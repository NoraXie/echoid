import redis.asyncio as redis
import random
import string
import json
from .config import settings

# Initialize Redis client
redis_client = redis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)

async def generate_token(length=None):
    """
    Generate Secure Token:
    - Length: 6-10 chars (randomly selected if not specified)
    - Charset: A-Z (Upper) + 0-9
    - Exclude: I, L, 1, O, 0
    - Constraint: At least 4 digits
    """
    if length is None:
        length = random.choice([6, 7, 8, 9, 10])
    
    # Allowed chars (excluding I, L, 1, O, 0)
    allowed_letters = "ABCDEFGHJKMNPQRSTUVWXYZ" # No I, L, O
    allowed_digits = "23456789" # No 1, 0
    
    while True:
        # Generate random mix
        token_chars = []
        # Ensure at least 4 digits
        for _ in range(4):
            token_chars.append(random.choice(allowed_digits))
            
        # Fill the rest
        if length > 4:
            for _ in range(length - 4):
                token_chars.append(random.choice(allowed_letters + allowed_digits))
            
        random.shuffle(token_chars)
        token = "".join(token_chars)
        
        # Double check constraints (just in case)
        digit_count = sum(c.isdigit() for c in token)
        if digit_count >= 4:
            return token

async def generate_otp(length=4):
    return ''.join(random.choices(string.digits, k=length))

import hashlib
import base64

# ... existing imports ...

def validate_pkce(verifier: str, challenge: str) -> bool:
    """
    Validate PKCE Code Verifier against Challenge (S256)
    """
    if not verifier or not challenge:
        return False
    # SHA256(verifier) -> Base64URL-encoded
    sha256 = hashlib.sha256(verifier.encode('utf-8')).digest()
    # Python's urlsafe_b64encode adds padding '=', standard PKCE usually strips it
    computed_challenge = base64.urlsafe_b64encode(sha256).decode('utf-8').rstrip('=')
    return computed_challenge == challenge

async def save_verification_session(token: str, phone: str, tenant_id: int = None, code_challenge: str = None):
    # PRD v5.0: Redis.setex("session:LOGIN-82910", 600, phone_number)
    # Update: Store JSON to include tenant_id for billing
    key = f"session:{token}"
    data = {"phone": phone}
    if tenant_id is not None:
        data["tenant_id"] = tenant_id
    if code_challenge:
        data["code_challenge"] = code_challenge
        
    await redis_client.setex(key, 600, json.dumps(data))


async def get_session_data(token: str):
    key = f"session:{token}"
    data_str = await redis_client.get(key)
    if not data_str:
        return None
    try:
        return json.loads(data_str)
    except json.JSONDecodeError:
        # Handle legacy string format
        return {"phone": data_str, "tenant_id": None}

async def get_session_phone(token: str):
    data = await get_session_data(token)
    if data:
        return data.get("phone")
    return None

async def acquire_lock(msg_id: str, ttl=3600) -> bool:
    # PRD v5.0: Redis.setnx("lock:{msg_id}", 1)
    key = f"lock:{msg_id}"
    success = await redis_client.setnx(key, "1")
    if success:
        await redis_client.expire(key, ttl)
    return success

async def get_random_template() -> str:
    # PRD v5.0: Redis.srandmember("templates:es_mx")
    template = await redis_client.srandmember("templates:es_mx")
    if not template:
        # Fallback
        return "Tu código {app_name} es {otp}. {link}"
    return template

async def check_rate_limit(identifier: str, limit: int, period: int) -> bool:
    """
    Simple fixed window rate limiter.
    Returns True if allowed, False if limit exceeded.
    """
    key = f"ratelimit:{identifier}"
    current = await redis_client.incr(key)
    if current == 1:
        await redis_client.expire(key, period)
    
    return current <= limit
