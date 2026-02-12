import os
import sys
import time
from sqlalchemy.exc import OperationalError

# Since we run this as `python -m server.scripts.init_db` with PYTHONPATH=/app,
# we can import directly from the server package.
from server.database import engine, SessionLocal
from server.models import Base, Tenant
from server.utils import generate_token

def wait_for_db():
    retries = 30
    while retries > 0:
        try:
            conn = engine.connect()
            conn.close()
            print("Database connection successful.")
            return True
        except OperationalError:
            print(f"Database not ready yet. Retrying in 2 seconds... ({retries} left)")
            time.sleep(2)
            retries -= 1
    return False

def init_db():
    if not wait_for_db():
        print("Could not connect to database. Exiting.")
        sys.exit(1)

    print("Creating tables...")
    Base.metadata.create_all(bind=engine)
    print("Tables created.")
    
    # Create initial tenant if not exists
    db = SessionLocal()
    try:
        # Check if any tenant exists
        existing_tenant = db.query(Tenant).first()
        if not existing_tenant:
            print("Creating default tenant...")
            # Use environment variables for sensitive initial data if available, 
            # or generate secure defaults.
            default_api_key = os.getenv("DEFAULT_TENANT_KEY", "test_key_123")
            
            tenant = Tenant(
                api_key=default_api_key,
                name="Default Tenant",
                balance=100.0
            )
            db.add(tenant)
            db.commit()
            print(f"Default tenant created. API Key: {default_api_key}")
        else:
            print("Tenant already exists. Skipping creation.")
            
    except Exception as e:
        print(f"Error initializing data: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    init_db()
