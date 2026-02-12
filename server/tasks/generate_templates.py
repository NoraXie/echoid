import asyncio
import httpx
import redis.asyncio as redis
import sys
import os

# Allow importing from server package
sys.path.append("/app")

try:
    from server.config import settings
    from server.database import SessionLocal, engine
    from server.models import Base, Template
except ImportError:
    # Fallback for local run
    sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
    from server.config import settings
    from server.database import SessionLocal, engine
    from server.models import Base, Template

# Ensure tables exist (for standalone script run)
Base.metadata.create_all(bind=engine)

REDIS_KEY_TEMPLATES = "templates:es_mx"
TARGET_COUNT = 20

# --- Prompt Engineering Section ---
# This system prompt controls the persona and output format of the LLM.
# Load from external markdown file for easier editing.
try:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    prompt_path = os.path.join(current_dir, "copywriter_prompts.md")
    with open(prompt_path, "r", encoding="utf-8") as f:
        PROMPT_SYSTEM = f.read()
except Exception as e:
    print(f"Error loading prompt file: {e}")
    sys.exit(1)

async def save_to_db(content: str):
    """Save template to PostgreSQL asynchronously (simulated via sync session in thread)."""
    # This wrapper is actually problematic if called with run_in_executor(None, lambda: asyncio.run(...))
    # It's better to make the DB logic purely sync and call it with run_in_executor
    pass

def save_to_db_sync(content: str):
    try:
        db = SessionLocal()
        # Check for duplicates
        exists = db.query(Template).filter(Template.content == content).first()
        if not exists:
            new_template = Template(content=content, language="es_mx", source="ai_generated")
            db.add(new_template)
            db.commit()
            return True
        return False
    except Exception as e:
        print(f"DB Error: {e}")
        return False
    finally:
        db.close()

async def generate_single_template(client: httpx.AsyncClient, index: int):
    # Mock Mode Support
    if settings.NVIDIA_API_KEY.startswith("mock-"):
        import random
        templates = [
            "Hola, tu código {app_name} es {otp}. Entra aquí: {link}",
            "Verificación {app_name}: usa {otp} para entrar. Link: {link}",
            "Aquí tienes tu acceso a {app_name}: {otp}. {link}",
            "Código de seguridad {app_name}: {otp}. No lo compartas. {link}",
            "¡Listo! Tu clave {app_name} es {otp}. Haz clic: {link}"
        ]
        return random.choice(templates)

    # User Instruction with Random Seed Injection
    user_instruction = f"Generate variation #{index}. Make this one {'very short' if index%2==0 else 'friendly'}. Use {'Mexican' if index%3==0 else 'Colombian'} slang."

    try:
        response = await client.post(
            f"{settings.NVIDIA_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.NVIDIA_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "meta/llama3-70b-instruct", # Optimized for Llama 3 70B
                "messages": [
                    {"role": "system", "content": PROMPT_SYSTEM},
                    {"role": "user", "content": user_instruction}
                ],
                "temperature": 0.95, # 🔥 High temperature = High randomness
                "top_p": 0.9,
                "max_tokens": 60
            },
            timeout=10.0
        )
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"].strip()
        # Remove surrounding quotes if present
        if content.startswith('"') and content.endswith('"'):
            content = content[1:-1]
        return content
    except Exception as e:
        print(f"Error generating template: {e}")
        return None

def validate_template(text: str) -> bool:
    if not text:
        return False
    required = ["{app_name}", "{otp}", "{link}"]
    for req in required:
        if req not in text:
            return False
    return True

async def main():
    print(f"Starting Offline Template Factory...")
    print(f"Target: {TARGET_COUNT} new templates")
    
    # Use Redis URL from settings which already includes password if set
    redis_client = redis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
    
    # Test Redis Connection
    try:
        await redis_client.ping()
        print("Redis connection successful.")
    except Exception as e:
        print(f"Redis connection failed: {e}")
        return

    async with httpx.AsyncClient() as client:
        generated = 0
        attempts = 0
        
        while generated < TARGET_COUNT and attempts < TARGET_COUNT * 2:
            attempts += 1
            # Generate Template
            text = await generate_single_template(client, attempts)
            
            # Validate Format
            if validate_template(text):
                # 1. Save to Redis (for high-speed random access)
                redis_added = await redis_client.sadd(REDIS_KEY_TEMPLATES, text)
                
                # 2. Save to Postgres (for persistence/audit)
                # We run this even if Redis has it, to ensure DB is consistent
                # Using run_in_executor to avoid blocking async loop with sync DB calls
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, save_to_db_sync, text)
                
                if redis_added > 0:
                    generated += 1
                    print(f"[{generated}/{TARGET_COUNT}] Saved to Redis & DB: {text[:50]}...")
                else:
                    print(f"Duplicate in Redis (skipped).")
            else:
                print(f"Invalid format or generation failed.")
                
    total = await redis_client.scard(REDIS_KEY_TEMPLATES)
    print(f"Job Complete. Total templates in Redis: {total}")
    
    # Verify by reading back 3 random templates
    print("\n--- Verification: Random 3 Templates from Redis ---")
    samples = await redis_client.srandmember(REDIS_KEY_TEMPLATES, 3)
    for i, s in enumerate(samples, 1):
        print(f"{i}. {s}")
        
    await redis_client.aclose()

if __name__ == "__main__":
    asyncio.run(main())
