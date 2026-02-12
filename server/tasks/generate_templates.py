import asyncio
import httpx
import redis.asyncio as redis
import sys
import os

# Allow importing from server package
sys.path.append("/app")

try:
    from server.config import settings
except ImportError:
    # Fallback for local run
    sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
    from server.config import settings

REDIS_KEY_TEMPLATES = "templates:es_mx"
TARGET_COUNT = 20

# --- Prompt Engineering Section ---
# This system prompt controls the persona and output format of the LLM.
# Adjust this to change the style, language, or constraints of the generated templates.
PROMPT_SYSTEM = """You are a Mexican cybersecurity assistant. Generate a unique, short WhatsApp verification message in Spanish (MX).
Rules:
1. You MUST include these exact placeholders: {app_name}, {otp}, {link}. Do NOT fill them.
2. Vary the tone: Formal, Casual, Urgent, or Friendly.
3. Use local slang occasionally (e.g., 'Chécalo', 'Oye').
4. Output ONLY the raw text. Do not include quotes or explanations."""

async def generate_single_template(client: httpx.AsyncClient):
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

    try:
        response = await client.post(
            f"{settings.NVIDIA_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.NVIDIA_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": settings.NVIDIA_MODEL,
                "messages": [{"role": "system", "content": PROMPT_SYSTEM}],
                "temperature": 0.9, # High creativity
                "max_tokens": 100
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
            text = await generate_single_template(client)
            
            # Validate Format
            if validate_template(text):
                # Add to Redis Set (automatically handles deduplication)
                added = await redis_client.sadd(REDIS_KEY_TEMPLATES, text)
                if added > 0:
                    generated += 1
                    print(f"[{generated}/{TARGET_COUNT}] Added: {text[:50]}...")
                else:
                    print(f"Duplicate skipped.")
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
