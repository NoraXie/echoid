import asyncio
import httpx
import redis.asyncio as redis
import sys
import os
import random
import string

# Allow importing from server package
sys.path.append("/app")

try:
    from server.config import settings
    from server.database import SessionLocal, engine
    from server.models import Base, Template
    from server.utils import generate_token
except ImportError:
    # Fallback for local run
    sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
    from server.config import settings
    from server.database import SessionLocal, engine
    from server.models import Base, Template
    from server.utils import generate_token

# Ensure tables exist (for standalone script run)
Base.metadata.create_all(bind=engine)

REDIS_KEY_TEMPLATES_DOWNSTREAM = "templates:es_mx"
REDIS_KEY_TEMPLATES_UPSTREAM = "templates:es_mx:upstream"
TARGET_COUNT = 20

# --- Prompt Loading ---
def load_prompt(filename):
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        prompt_path = os.path.join(current_dir, filename)
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print(f"Error loading prompt file {filename}: {e}")
        sys.exit(1)

PROMPT_REPLY = load_prompt("prompts_reply.md")
PROMPT_TOKEN = load_prompt("prompts_random_token.md")

# --- Helper Functions ---
def save_to_db_sync(content: str, source_type: str):
    """
    source_type: 'ai_reply' (Downstream) or 'ai_request' (Upstream)
    """
    try:
        db = SessionLocal()
        # Check for duplicates
        exists = db.query(Template).filter(Template.content == content).first()
        if not exists:
            new_template = Template(content=content, language="es_mx", source=source_type)
            db.add(new_template)
            db.commit()
            return True
        return False
    except Exception as e:
        print(f"DB Error: {e}")
        return False
    finally:
        db.close()

# --- Generators ---

async def generate_downstream_reply(client: httpx.AsyncClient, index: int):
    """Downstream Factory: System Reply"""
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

    user_instruction = f"Generate variation #{index}. Make this one {'very short' if index%2==0 else 'friendly'}. Use {'Mexican' if index%3==0 else 'Colombian'} slang."
    
    try:
        response = await client.post(
            f"{settings.NVIDIA_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.NVIDIA_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": settings.NVIDIA_MODEL,
                "messages": [
                    {"role": "system", "content": PROMPT_REPLY},
                    {"role": "user", "content": user_instruction}
                ],
                "temperature": 0.95,
                "top_p": 0.9,
                "max_tokens": 60
            },
            timeout=10.0
        )
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"].strip()
        return content
    except Exception as e:
        print(f"Downstream Gen Error: {e}")
        return None

async def generate_upstream_request(client: httpx.AsyncClient, index: int):
    """Upstream Factory: User Request"""
    token = await generate_token()
    
    # Mock Mode Support
    if settings.NVIDIA_API_KEY.startswith("mock-"):
        templates = [
            f"Hola, mi código es {token}",
            f"Aquí está el código: {token}",
            f"Verifícame con {token}",
            f"{token}",
            f"Ya tengo el código {token}, gracias"
        ]
        return random.choice(templates)

    user_instruction = f"Generate variation #{index}. The token is {token}."
    
    try:
        response = await client.post(
            f"{settings.NVIDIA_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.NVIDIA_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": settings.NVIDIA_MODEL,
                "messages": [
                    {"role": "system", "content": PROMPT_TOKEN},
                    {"role": "user", "content": user_instruction}
                ],
                "temperature": 0.9,
                "max_tokens": 40
            },
            timeout=10.0
        )
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"].strip()
        # Ensure token is preserved exactly (LLM might mess it up slightly, though unlikely with instructions)
        if token not in content:
            # Fallback if token lost: just append it
            content = f"{content} {token}"
        return content
    except Exception as e:
        print(f"Upstream Gen Error: {e}")
        return None

async def main():
    print("🚀 Starting Template Factory...")
    redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    
    async with httpx.AsyncClient() as client:
        # 1. Generate Downstream (Replies)
        print("\n--- Generating Downstream Replies (System -> User) ---")
        count_down = 0
        for i in range(TARGET_COUNT):
            content = await generate_downstream_reply(client, i)
            if content:
                # Save to Redis (List)
                await redis_client.rpush(REDIS_KEY_TEMPLATES_DOWNSTREAM, content)
                # Save to DB
                if save_to_db_sync(content, "ai_reply"):
                    print(f"✅ [Downstream] Saved: {content[:30]}...")
                    count_down += 1
                else:
                    print(f"⚠️ [Downstream] Duplicate/Error")
        
        # 2. Generate Upstream (Requests)
        print("\n--- Generating Upstream Requests (User -> System) ---")
        count_up = 0
        for i in range(TARGET_COUNT):
            content = await generate_upstream_request(client, i)
            if content:
                # Save to Redis (List)
                await redis_client.rpush(REDIS_KEY_TEMPLATES_UPSTREAM, content)
                # Save to DB
                if save_to_db_sync(content, "ai_request"):
                    print(f"✅ [Upstream] Saved: {content[:30]}...")
                    count_up += 1
                else:
                    print(f"⚠️ [Upstream] Duplicate/Error")

    print(f"\n🎉 Done! Downstream: {count_down}, Upstream: {count_up}")
    await redis_client.aclose()

if __name__ == "__main__":
    asyncio.run(main())
