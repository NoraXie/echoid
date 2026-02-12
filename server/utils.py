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

async def save_verification_session(token: str, phone: str, tenant_id: int = None):
    # PRD v5.0: Redis.setex("session:LOGIN-82910", 600, phone_number)
    # Update: Store JSON to include tenant_id for billing
    key = f"session:{token}"
    if tenant_id is not None:
        data = {"phone": phone, "tenant_id": tenant_id}
        await redis_client.setex(key, 600, json.dumps(data))
    else:
        # Backward compatibility or simple string if no tenant_id provided (should generally be avoided in v5)
        await redis_client.setex(key, 600, phone)

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
