import asyncio
import httpx
import redis.asyncio as redis
import sys
import os

# Add project root (echoid) to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from server.config import settings

REDIS_KEY_TEMPLATES = "templates:es_mx"
TARGET_COUNT = 200

# NVIDIA NIM Configuration (Example endpoint, replace with actual if known)
# Assuming OpenAI-compatible endpoint for Llama 3 70B
NIM_BASE_URL = "https://integrate.api.nvidia.com/v1" 
MODEL_NAME = "meta/llama3-70b-instruct"

PROMPT_SYSTEM = """You are a Mexican cybersecurity assistant. Generate a unique, short WhatsApp verification message in Spanish (MX).
Rules:
1. You MUST include these exact placeholders: {app_name}, {otp}, {link}. Do NOT fill them.
2. Vary the tone: Formal, Casual, Urgent, or Friendly.
3. Use local slang occasionally (e.g., 'Chécalo', 'Oye').
4. Output ONLY the raw text."""

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
            f"{NIM_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.NVIDIA_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": MODEL_NAME,
                "messages": [{"role": "system", "content": PROMPT_SYSTEM}],
                "temperature": 0.9, # High creativity
                "max_tokens": 100
            },
            timeout=10.0
        )
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"].strip()
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
    
    redis_client = redis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
    
    async with httpx.AsyncClient() as client:
        generated = 0
        attempts = 0
        
        while generated < TARGET_COUNT and attempts < TARGET_COUNT * 2:
            attempts += 1
            text = await generate_single_template(client)
            
            if text and validate_template(text):
                # Add to Redis Set (automatically handles deduplication)
                added = await redis_client.sadd(REDIS_KEY_TEMPLATES, text)
                if added > 0:
                    generated += 1
                    print(f"[{generated}/{TARGET_COUNT}] Added: {text[:30]}...")
                else:
                    print(f"Duplicate skipped.")
            else:
                print(f"Invalid format skipped: {text}")
                
    print(f"Job Complete. Total templates in Redis: {await redis_client.scard(REDIS_KEY_TEMPLATES)}")
    await redis_client.aclose()

if __name__ == "__main__":
    asyncio.run(main())
