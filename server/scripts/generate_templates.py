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
    print(f"Connecting to Redis at {settings.REDIS_URL}...")
    redis_client = redis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)

    try:
        # Check if the key exists and if it is of the correct type (Set)
        key_type = await redis_client.type(REDIS_KEY_TEMPLATES_DOWNSTREAM)
        if key_type == "list":
             print(f"Warning: Key {REDIS_KEY_TEMPLATES_DOWNSTREAM} is a List. Deleting it to create a Set.")
             await redis_client.delete(REDIS_KEY_TEMPLATES_DOWNSTREAM)
        elif key_type != "none" and key_type != "set":
             print(f"Error: Key {REDIS_KEY_TEMPLATES_DOWNSTREAM} is of type {key_type}. Expected Set or None.")
             # Depending on your requirement, you might want to delete it or exit
             # For now, let's delete it to self-heal
             print(f"Self-healing: Deleting incorrect key type...")
             await redis_client.delete(REDIS_KEY_TEMPLATES_DOWNSTREAM)

        async with httpx.AsyncClient() as client:
            # 1. Generate Downstream (Replies)
            print("\n--- Generating Downstream Replies (System -> User) ---")
            count_down = 0
            tasks = [generate_downstream_reply(client, i) for i in range(TARGET_COUNT)]
            results = await asyncio.gather(*tasks)

            for content in results:
                if content:
                    # Save to Redis (Set)
                    # SADD returns 1 if added, 0 if duplicate
                    if await redis_client.sadd(REDIS_KEY_TEMPLATES_DOWNSTREAM, content):
                        # Save to DB
                        if save_to_db_sync(content, "ai_reply"):
                            print(f"✅ [Downstream] Saved: {content[:30]}...")
                            count_down += 1
                        else:
                            print(f"⚠️ [Downstream] DB Duplicate")
                    else:
                         print(f"⚠️ [Downstream] Redis Duplicate")

            # 2. Generate Upstream (Requests)
            # Upstream templates (User messages) can probably stay as a list or also become a set
            # Let's keep them as list for now or convert to set if uniqueness is desired
            # But the error was specifically about WRONGTYPE on rpush vs set
            # Assuming upstream logic uses RPUSH, let's check its key type too
            
            key_type_up = await redis_client.type(REDIS_KEY_TEMPLATES_UPSTREAM)
            if key_type_up == "set": # If we want list but it is set
                 print(f"Warning: Key {REDIS_KEY_TEMPLATES_UPSTREAM} is a Set. Deleting it to create a List.")
                 await redis_client.delete(REDIS_KEY_TEMPLATES_UPSTREAM)

            print("\n--- Generating Upstream Requests (User -> System) ---")
            count_up = 0
            tasks_up = [generate_upstream_request(client, i) for i in range(TARGET_COUNT)]
            results_up = await asyncio.gather(*tasks_up)
            
            for content in results_up:
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
    
    finally:
        await redis_client.aclose()

if __name__ == "__main__":
    asyncio.run(main())
