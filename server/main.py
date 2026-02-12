import asyncio
import re
import logging
import time
import json
import secrets
import random
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks, Depends
from fastapi.responses import RedirectResponse, JSONResponse
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
from .schemas import InitRequest, InitResponse
from .utils import (
    generate_token, generate_otp, save_verification_session, 
    get_session_data, acquire_lock, get_random_template, check_rate_limit,
    redis_client
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

class VerifyRequest(BaseModel):
    token: str
    otp: str

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

    # 1. Idempotency Check
    if not await acquire_lock(msg_id):
        return {"status": "ok", "msg": "duplicate"}

    # 2. Token Extraction
    # Match LOGIN-\d+ (case insensitive)
    match = re.search(r"(LOGIN-\d+)", body, re.IGNORECASE)
    if not match:
        return {"status": "ignored", "msg": "no_token"}
        
    token = match.group(1).upper()
    
    # 3. Retrieve Session & Tenant Info
    session_data = await get_session_data(token)
    if not session_data:
        # Session expired or invalid
        return {"status": "ignored", "msg": "session_not_found"}
        
    tenant_id = session_data.get("tenant_id")
    
    # Update Session with Verified WA ID
    session_data["wa_id"] = sender
    await redis_client.setex(f"session:{token}", 600, json.dumps(session_data))
    
    logger.info(f"Processing for Tenant: {tenant_id}, Token: {token}, WA_ID: {sender}")

    # 4. Humanize
    await echob_client.start_typing("default", sender)
    await asyncio.sleep(2.5) # Simulate Human behavior (typing delay)
    await echob_client.stop_typing("default", sender)

    # 5. Prepare Material
    otp = await generate_otp()
    
    # Save OTP for verification (Web Demo support)
    await redis_client.setex(f"otp:{token}", 300, otp)
    
    # Anti-Ban Strategy: Slug Short Link
    slug = secrets.token_urlsafe(6) # e.g. "Hu7_9A"
    await redis_client.setex(f"short:{slug}", 300, json.dumps({"token": token, "otp": otp}))
    
    # Domain Rotation
    base_url = settings.HOST_URL
    if settings.LINK_DOMAINS:
        domains = [d.strip() for d in settings.LINK_DOMAINS.split(",") if d.strip()]
        if domains:
            base_url = random.choice(domains)
            
    if not base_url.startswith("http"):
        base_url = f"http://{base_url}"
        
    link = f"{base_url}/q/{slug}"
    
    # Get Tenant Name (We need to query DB or cache it. For MVP, query DB or use placeholder if not critical)
    app_name = "EchoID App" 
    
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
    # Limit: 5 requests per 60 seconds per phone
    if not await check_rate_limit(f"init:{request.phone}", limit=5, period=60):
        raise HTTPException(status_code=429, detail="Too many requests")

    # 1. Auth & Balance Check
    tenant = db.query(Tenant).filter(Tenant.api_key == request.api_key).first()
    if not tenant:
        raise HTTPException(status_code=403, detail="Invalid API Key")
    
    if tenant.balance <= 0:
        raise HTTPException(status_code=402, detail="Insufficient balance")
    
    # 2. Generate Session
    token = await generate_token() # LOGIN-XXXXX
    
    # 3. Cache
    await save_verification_session(token, request.phone, tenant.id)
    
    # 4. Build Deep Link
    # PRD example: "https://wa.me/52155...?text=LOGIN-82910"
    # Assuming request.phone is raw number. If we need country code logic, we'd add it here.
    # For now, we trust the input or prepend '521' if it looks like a Mexican number (10 digits starting with 55?).
    # Let's just use the phone as provided but ensure 521 prefix if it's MX target.
    # To be safe and simple:
    target_phone = request.phone
    if not target_phone.startswith("52") and len(target_phone) == 10:
        target_phone = "521" + target_phone
        
    deep_link = f"https://wa.me/{target_phone}?text={token}" 
    
    return InitResponse(deep_link=deep_link)

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
        
    # Retrieve WA ID from session if available
    session_data = await get_session_data(request.token)
    wa_id = session_data.get("wa_id") if session_data else None

    return {"status": "verified", "wa_id": wa_id}

@app.get("/q/{slug}")
async def short_link_handler(slug: str):
    """
    Anti-Ban Short Link Redirect
    """
    data_str = await redis_client.get(f"short:{slug}")
    if not data_str:
        return JSONResponse({"error": "Link expired or invalid"}, status_code=404)
    
    try:
        data = json.loads(data_str)
        token = data.get('token')
        otp = data.get('otp')
        
        if not token or not otp:
             return JSONResponse({"error": "Invalid link data"}, status_code=400)

        # 302 Redirect to Custom Scheme
        # This happens in browser, safe from WhatsApp scanner
        target = f"echoid://login?token={token}&otp={otp}"
        return RedirectResponse(url=target, status_code=302)
    except Exception:
        return JSONResponse({"error": "Server error"}, status_code=500)

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
