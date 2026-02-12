import asyncio
import sys
import os
import redis.asyncio as redis

# Allow importing from server package
sys.path.append("/app")

try:
    from server.config import settings
    from server.database import SessionLocal
    from server.models import Template
except ImportError:
    # Fallback for local run
    sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
    from server.config import settings
    from server.database import SessionLocal
    from server.models import Template

REDIS_KEY_TEMPLATES = "templates:es_mx"

async def clear_templates():
    print(f"Connecting to Redis at {settings.REDIS_URL}...")
    redis_client = redis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
    
    try:
        # 1. Clear Redis
        count = await redis_client.scard(REDIS_KEY_TEMPLATES)
        if count == 0:
            print(f"[Redis] No templates found in '{REDIS_KEY_TEMPLATES}'.")
        else:
            print(f"[Redis] Found {count} templates. Deleting...")
            await redis_client.delete(REDIS_KEY_TEMPLATES)
            print(f"[Redis] Successfully deleted key: {REDIS_KEY_TEMPLATES}")
            
        # 2. Clear Postgres
        print("[DB] Clearing 'templates' table in Postgres...")
        # Using sync session in async context requires run_in_executor
        loop = asyncio.get_event_loop()
        deleted_count = await loop.run_in_executor(None, clear_db_templates)
        print(f"[DB] Deleted {deleted_count} rows from 'templates' table.")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await redis_client.aclose()

def clear_db_templates():
    try:
        db = SessionLocal()
        # Delete all records from Template table
        # If we only want to delete generated ones: .filter(Template.source == "ai_generated")
        # But user said "clear history", implying all. Let's stick to "es_mx" + "ai_generated" to be safe or just all.
        # Looking at generate_templates.py: new_template = Template(content=content, language="es_mx", source="ai_generated")
        
        deleted = db.query(Template).filter(Template.language == "es_mx", Template.source == "ai_generated").delete()
        db.commit()
        return deleted
    except Exception as e:
        print(f"DB Error: {e}")
        return 0
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(clear_templates())
