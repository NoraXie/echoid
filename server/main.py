import asyncio
import re
import logging
import time
import json
import secrets
import random
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks, Depends
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel

# Configure Logging with UTC/Local Time fix
logging.Formatter.converter = time.localtime
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("echoid")

from .config import settings
from .schemas import InitRequest, InitResponse, VerifyRequest
from .utils import (
    generate_token, generate_otp, save_verification_session, 
    get_session_data, acquire_lock, get_random_template, check_rate_limit,
    redis_client, validate_pkce
)
from .echob_client import echob_client
from .database import get_db, SessionLocal
from .models import Tenant, Log

app = FastAPI(title=settings.PROJECT_NAME, version=settings.VERSION)

@app.on_event("startup")
async def startup_event():
    logger.info(f"Server starting up...")
    logger.info(f"Config HOST_URL: {settings.HOST_URL}")
    logger.info(f"Config ECHOB_API_URL: {settings.ECHOB_API_URL}")

@app.get("/")
async def root():
    return {"message": "EchoID Server is running", "version": settings.VERSION}

# --- Simulation Schema ---
class SimulationRequest(BaseModel):
    phone: str
    token: str

@app.post("/v1/simulate/user-send-message")
async def simulate_user_send_message(request: SimulationRequest, background_tasks: BackgroundTasks):
    """
    Simulation Endpoint for EchoID Demo App.
    Instead of real WhatsApp -> EchoB -> Webhook,
    the Demo App calls this to simulate "User sent LOGIN-XXXX to WhatsApp".
    """
    # Construct a mock EchoB payload
    # PRD Payload structure (simplified assumption):
    # {
    #   "sender": "52155...", 
    #   "text": "LOGIN-XXXXX",
    #   "timestamp": ...
    # }
    import time
    
    mock_payload = {
        "sender": request.phone,
        "text": request.token,
        "timestamp": int(time.time())
    }
    
    # We can directly call the webhook logic function if we refactor it, 
    # or just forward the request internally (but FastAPI doesn't easily do internal forwarding).
    # Better: Extract the core logic of webhook into a function and call it.
    
    # However, to keep it simple and reuse existing endpoint, we can use httpx to call localhost
    # But that adds network overhead. Let's just refactor the webhook logic slightly or
    # better yet, simply inject the payload into the processing function if we can.
    
    # Let's verify if we can just re-use the webhook handler logic.
    # The webhook handler takes a Request object. We can mock it.
    
    # Actually, for a demo, it's cleaner to just have this endpoint call the processing logic directly.
    # But since the webhook logic is inside `echob_webhook`, let's see its implementation.
    
    # Wait, I need to see the implementation of echob_webhook first to extract logic.
    # For now, let's just make this endpoint receive the request and print it, 
    # then I'll refactor the webhook to share logic.
    
    # Let's assume we will refactor `process_webhook_payload`
    await process_webhook_payload(mock_payload, background_tasks)
    
    return {"status": "simulated", "detail": "Message received and processed"}

async def process_webhook_payload(payload: dict, background_tasks: BackgroundTasks):
    """
    Core logic for processing incoming messages (from real Webhook or Simulation).
    """
    # Basic Validation (Adapted for internal dict payload)
    # Simulation payload structure matches EchoB structure?
    # EchoB payload: {"event": "message", "payload": {"from": "...", "body": "...", "id": "..."}}
    # Our simulation mock_payload was: {"sender": "...", "text": "...", "timestamp": ...}
    # Let's unify them or adapt here.
    
    # If it's real webhook:
    event_type = payload.get("event")
    
    # If it's simulation (no "event" key or custom structure), we adapt
    if "sender" in payload and "text" in payload:
        # Simulation structure adaptation
        sender = payload["sender"]
        body = payload["text"]
        msg_id = f"sim-{payload['timestamp']}"
    else:
        # Real Webhook structure
        if event_type != "message":
            return {"status": "ignored"}
        message_data = payload.get("payload", {})
        body = message_data.get("body", "")
        sender = message_data.get("from", "") 
        msg_id = message_data.get("id", "")

    if not body or not sender or not msg_id:
        return {"status": "ignored"}

    # Optimization 1: Rate Limit (DoS Protection) - Limit ALL incoming messages from sender
    # Limit: Requests per period (configurable)
    if not await check_rate_limit(f"webhook:{sender}", limit=settings.RATE_LIMIT_WEBHOOK, period=settings.RATE_LIMIT_WEBHOOK_PERIOD):
        logger.warning(f"Rate limit exceeded for sender: {sender}")
        return {"status": "ignored", "msg": "rate_limit_exceeded"}

    # Optimization 2: CPU-based Token Extraction (Avoid Redis if no token)
    match = re.search(r"\b([A-HJ-KMNP-Z2-9]{6,10})\b", body, re.IGNORECASE)
    if not match:
        return {"status": "ignored", "msg": "no_token"}
    
    token = match.group(1).upper()

    # 3. Idempotency Check
    if not await acquire_lock(msg_id):
        return {"status": "ok", "msg": "duplicate"}

    # 4. Retrieve Session & Tenant Info
    session_data = await get_session_data(token)
    if not session_data:
        # Session expired or invalid
        return {"status": "ignored", "msg": "session_not_found"}

    # Security: Session Hijack Prevention
    # If session is already claimed by a WA ID, and it's NOT the current sender -> Attack attempt!
    if session_data.get("wa_id") and session_data.get("wa_id") != sender:
        logger.warning(f"Session Hijack Attempt! Token: {token}, Owner: {session_data.get('wa_id')}, Attacker: {sender}")
        return {"status": "ignored", "msg": "token_already_claimed"}
    
    # Security: Phone Number Mismatch Prevention (User A initiates, User B sends message)
    # The session must belong to the sender.
    expected_phone = session_data.get("phone")
    sender_clean = sender.split("@")[0]
    
    if expected_phone:
        # Normalize: Remove @s.whatsapp.net for comparison if needed
        expected_clean = expected_phone.split("@")[0]
        
        if expected_clean != sender_clean:
             logger.warning(f"Phone Mismatch! Token: {token}, Expected: {expected_clean}, Sender: {sender_clean}")
             return {"status": "ignored", "msg": "phone_mismatch"}
    else:
        # If no phone was provided at init (or not yet bound), we bind the first sender as the owner
        # This effectively "registers" the user with this phone number for this session
        session_data["phone"] = sender
        # Update session in Redis to save the binding
        await redis_client.setex(f"session:{token}", settings.SESSION_TTL, json.dumps(session_data))

    tenant_id = session_data.get("tenant_id")
    
    # Update Session with Verified WA ID
    session_data["wa_id"] = sender
    await redis_client.setex(f"session:{token}", settings.SESSION_TTL, json.dumps(session_data))
    
    logger.info(f"Processing for Tenant: {tenant_id}, Token: {token}, WA_ID: {sender}")

    # 4. Humanize
    await echob_client.start_typing("default", sender)
    await asyncio.sleep(2.5) # Simulate Human behavior (typing delay)
    await echob_client.stop_typing("default", sender)

    # 5. Prepare Material
    otp = await generate_otp()
    
    # Save OTP for verification (Web Demo support)
    await redis_client.setex(f"otp:{token}", settings.OTP_TTL, otp)
    
    # Anti-Ban Strategy: Slug Short Link
    slug = secrets.token_urlsafe(6) # e.g. "Hu7_9A"
    await redis_client.setex(f"short:{slug}", settings.SHORT_LINK_TTL, json.dumps({"token": token, "otp": otp}))
    
    # Domain Rotation
    base_url = settings.HOST_URL
    if settings.LINK_DOMAINS:
        domains = [d.strip() for d in settings.LINK_DOMAINS.split(",") if d.strip()]
        if domains:
            base_url = random.choice(domains)
            
    if not base_url.startswith("http"):
        base_url = f"http://{base_url}"
        
    link = f"{base_url}/q/{slug}"
    
    # Get Tenant Name or App Name from session
    app_name = session_data.get("app_name", "EchoID App")
    
    # 6. Template Assembly
    template = await get_random_template()
    final_msg = template.format(app_name=app_name, otp=otp, link=link)
    logger.info(f"Selected template: {final_msg}")

    # 7. Send Reply
    await echob_client.send_text("default", sender, final_msg)

    # 8. Billing & Logging (Background Task)
    if tenant_id:
        background_tasks.add_task(
            log_transaction, 
            tenant_id=tenant_id, 
            phone=sender, 
            token=token, 
            otp=otp, 
            template=final_msg, 
            cost=0.05 # Mock cost per transaction
        )
    
    return {"status": "ok"}

# Helper for background task billing
def log_transaction(tenant_id: int, phone: str, token: str, otp: str, template: str, cost: float):
    db = SessionLocal()
    try:
        # Decrement balance
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if tenant:
            tenant.balance -= cost
            
        # Create log
        log_entry = Log(
            tenant_id=tenant_id,
            phone=phone,
            token=token,
            otp=otp,
            template_snapshot=template,
            cost=cost
        )
        db.add(log_entry)
        db.commit()
    except Exception as e:
        logger.error(f"Error in billing: {e}")
        db.rollback()
    finally:
        db.close()

@app.post("/v1/init", response_model=InitResponse)
async def init_verification(request: InitRequest, db: Session = Depends(get_db)):
    """
    PRD v5.0 Section 3.2.A: SDK Init Interface
    """
    # 0. Risk Control (Rate Limit)
    # Limit: Requests per period (configurable)
    # Note: Since phone is no longer required, we cannot rate limit by phone here.
    # We could rate limit by IP or API Key, but for now we skip phone-based rate limit.
    # if request.phone and not await check_rate_limit(f"init:{request.phone}", limit=settings.RATE_LIMIT_INIT, period=settings.RATE_LIMIT_INIT_PERIOD):
    #    raise HTTPException(status_code=429, detail="Too many requests")

    # 1. Auth & Balance Check
    tenant = db.query(Tenant).filter(Tenant.api_key == request.api_key).first()
    if not tenant:
        raise HTTPException(status_code=403, detail="Invalid API Key")
    
    if tenant.balance <= 0:
        raise HTTPException(status_code=402, detail="Insufficient balance")
    
    # 2. Generate Session
    token = await generate_token() # LOGIN-XXXXX
    
    # 3. Cache
    await save_verification_session(
        token=token, 
        phone=None, # Phone is NOT provided in Init
        tenant_id=tenant.id, 
        code_challenge=request.code_challenge,
        app_name=request.app_name,
        package_name=request.package_name
    )
    
    # 4. Build Deep Link (EchoID Redirect Link)
    # Use EchoID domain to hide bot number and track clicks
    # Format: https://api.echoid.com/v1/go/{token}
    host = settings.HOST_URL.rstrip('/')
    deep_link = f"{host}/v1/go/{token}"
    
    logger.info(f"[Init] Token: {token} | App: {request.app_name}")
    
    return InitResponse(deep_link=deep_link)

@app.get("/v1/go/{token}")
async def go_redirect(token: str):
    """
    Redirects user to WhatsApp.
    Hides the bot phone number from the initial API response.
    """
    # 1. Validate Token
    session_data = await get_session_data(token)
    if not session_data:
        raise HTTPException(status_code=404, detail="Invalid or expired link")
    
    # 2. Construct WhatsApp Deep Link
    target_phone = settings.BOT_PHONE_NUMBER
    # Message MUST match the regex in webhook: \b([A-HJ-KMNP-Z2-9]{6,10})\b
    message = f"Hola, mi código de verificación es {token}"
    wa_link = f"https://wa.me/{target_phone}?text={message}"
    
    # 3. Redirect
    return RedirectResponse(url=wa_link)

@app.post("/v1/verify")
async def verify_otp(request: VerifyRequest):
    """
    Verify OTP for Web Demo (or App Manual Entry).
    """
    stored_otp = await redis_client.get(f"otp:{request.token}")
    if not stored_otp:
        # For security, we might want to return generic error, but for demo specific is fine
        raise HTTPException(status_code=400, detail="Invalid or expired session")
    
    if stored_otp != request.otp:
        raise HTTPException(status_code=400, detail="Invalid OTP")
        
    # Security: Invalidate OTP immediately after use (Replay Attack Prevention)
    await redis_client.delete(f"otp:{request.token}")

    # Retrieve WA ID from session if available
    session_data = await get_session_data(request.token)

    # PKCE Validation
    if session_data and session_data.get("code_challenge"):
        challenge = session_data.get("code_challenge")
        verifier = request.code_verifier
        if not verifier:
            raise HTTPException(status_code=400, detail="Missing code_verifier for secure session")
        if not validate_pkce(verifier, challenge):
            logger.warning(f"PKCE Validation Failed for Token {request.token}")
            raise HTTPException(status_code=403, detail="PKCE Validation Failed")

    wa_id = session_data.get("wa_id") if session_data else None

    return {"status": "verified", "wa_id": wa_id}

@app.get("/q/{slug}", response_class=HTMLResponse)
async def short_link_handler(slug: str):
    """
    Anti-Ban Short Link Redirect with Open Graph Preview (Rich Link)
    """
    data_str = await redis_client.get(f"short:{slug}")
    if not data_str:
        return HTMLResponse(content="<h1>Link Expired or Invalid</h1>", status_code=404)
    
    try:
        data = json.loads(data_str)
        token = data.get('token')
        otp = data.get('otp')
        
        if not token or not otp:
             return HTMLResponse(content="<h1>Invalid Link Data</h1>", status_code=400)

        # Custom Scheme Target (iOS / Fallback)
        target = f"echoid://login?token={token}&otp={otp}"
        
        # Retrieve Session Data to get Package Name (Dynamic per app)
        session_data = await get_session_data(token)
        package_name = None
        if session_data:
            package_name = session_data.get("package_name")
        
        # Fallback to Global Config if not in session
        if not package_name:
            package_name = settings.ANDROID_PACKAGE_NAME

        # Construct Android Intent URL (More reliable on Chrome/Android)
        # Format: intent://<host>/<path>?<query>#Intent;scheme=<scheme>;package=<package_name>;end;
        intent_url = None
        if package_name:
            intent_url = f"intent://login?token={token}&otp={otp}#Intent;scheme=echoid;package={package_name};end;"
        else:
            # Fallback Intent without package name
            intent_url = f"intent://login?token={token}&otp={otp}#Intent;scheme=echoid;end;"

        # Feature Flag: Use HTML Preview or Direct Redirect
        if settings.ENABLE_RICH_LINK_PREVIEW:
            # HTML with Open Graph Meta Tags for WhatsApp Preview
            image_url = "https://via.placeholder.com/300x200.png?text=Secure+Login"
            if not image_url.startswith("http"):
                image_url = f"{settings.HOST_URL.rstrip('/')}/{image_url.lstrip('/')}"
            
            canonical_url = f"{settings.HOST_URL.rstrip('/')}/q/{slug}"

            # JS Logic: Handle Android (Intent), iOS (Custom Scheme), and Web/Desktop
            html_content = f"""
            <!DOCTYPE html>
            <html prefix="og: http://ogp.me/ns#">
            <head>
                <meta property="og:title" content="Security Verification" />
                <meta property="og:description" content="Tap to verify your login request securely." />
                <meta property="og:image" content="{image_url}" />
                <meta property="og:url" content="{canonical_url}" />
                <meta property="og:type" content="website" />
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <title>Verifying...</title>
                <script>
                    var schemeUrl = "{target}";
                    var intentUrl = "{intent_url}";
                    
                    function launchApp() {{
                        var userAgent = navigator.userAgent || navigator.vendor || window.opera;
                        var isAndroid = /android/i.test(userAgent);
                        var isIOS = /iPad|iPhone|iPod/.test(userAgent) && !window.MSStream;

                        if (isAndroid) {{
                            // Android: Use Intent Scheme
                            window.location.href = intentUrl;
                        }} else if (isIOS) {{
                            // iOS: Use Custom Scheme
                            // Safari may prompt the user.
                            window.location.href = schemeUrl;
                        }} else {{
                            // Desktop / Web / Other
                            // Try custom scheme anyway (some desktop apps might handle it)
                            // But mainly rely on showing the manual button/msg
                            window.location.href = schemeUrl;
                        }}
                    }}

                    window.onload = function() {{
                        launchApp();
                        setTimeout(function() {{
                            document.getElementById('manual-link').style.display = 'block';
                            
                            // Check if desktop to show specific message
                            var userAgent = navigator.userAgent || navigator.vendor || window.opera;
                            var isMobile = /android|iPad|iPhone|iPod/i.test(userAgent);
                            if (!isMobile) {{
                                document.getElementById('desktop-msg').style.display = 'block';
                            }}
                        }}, 1000);
                    }};
                </script>
                <style>
                    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; text-align: center; padding: 20px; background-color: #f0f2f5; }}
                    .container {{ max-width: 400px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
                    h2 {{ color: #333; margin-bottom: 10px; }}
                    p {{ color: #666; margin-bottom: 20px; line-height: 1.5; }}
                    .btn {{ display: inline-block; padding: 15px 30px; background-color: #25D366; color: white; text-decoration: none; border-radius: 25px; font-size: 16px; font-weight: bold; transition: background-color 0.3s; width: 100%; box-sizing: border-box; }}
                    .btn:hover {{ background-color: #128C7E; }}
                    #manual-link {{ display: none; margin-top: 20px; }}
                    #desktop-msg {{ display: none; color: #888; font-size: 14px; margin-top: 15px; background: #fff3cd; padding: 10px; border-radius: 5px; border: 1px solid #ffeeba; color: #856404; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h2>Verifying Identity...</h2>
                    <p>We are redirecting you to the app to complete your login.</p>
                    
                    <div id="manual-link">
                        <a href="#" onclick="launchApp(); return false;" class="btn">Open App</a>
                    </div>

                    <div id="desktop-msg">
                        <p><strong>Note:</strong> This link is intended for the mobile app. If nothing happens, please open this link on your phone.</p>
                    </div>
                </div>
            </body>
            </html>
            """
            return HTMLResponse(content=html_content, status_code=200)
        else:
            # Fallback: 302 Redirect (Old Scheme)
            return RedirectResponse(url=target, status_code=302)

        # DO NOT DELETE immediately to allow Link Preview generation (Redis TTL handles expiration)
        # await redis_client.delete(f"short:{slug}")
    except Exception:
        return HTMLResponse(content="<h1>Server Error</h1>", status_code=500)

@app.get("/jump")
async def jump_link(t: str, o: str):
    """
    PRD v5.0 Section 3.2.C: Jump Interface
    Params: t=token, o=otp
    """
    # Logic: 302 Redirect to echoid://login?token={t}&otp={o}
    custom_scheme_url = f"echoid://login?token={t}&otp={o}"
    return RedirectResponse(url=custom_scheme_url, status_code=302)

@app.post("/webhook/echob")
async def echob_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    PRD v5.0 Section 3.2.B: WhatsApp Webhook
    """
    try:
        payload = await request.json()
    except:
        return {"status": "ignored"}

    return await process_webhook_payload(payload, background_tasks)
