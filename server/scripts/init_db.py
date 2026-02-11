import sys
import os
import time
from sqlalchemy.exc import OperationalError

# Adjust path to include the project root (echoid/server)
# In Docker, WORKDIR is /app, so adding /app to sys.path
sys.path.append("/app")

# Also try to append parent if running locally
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
sys.path.append(project_root)
sys.path.append(os.path.join(project_root, "echoid"))

from server.database import engine, SessionLocal
from server.models import Base, Tenant

def wait_for_db():
    retries = 30
    while retries > 0:
        try:
            # Try to connect
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
        print("Could not connect to database after multiple retries. Exiting.")
        sys.exit(1)

    print("Creating tables...")
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    try:
        # Check if test tenant exists
        test_api_key = os.getenv("TEST_TENANT_API_KEY", "test-api-key")
        # Only create if explicit env var is set or we are in dev/test (default)
        # In production, we might want to skip creating default test tenant unless specified
        
        tenant = db.query(Tenant).filter(Tenant.api_key == test_api_key).first()
        if not tenant:
            print(f"Creating initial tenant with key: {test_api_key[:4]}***")
            tenant = Tenant(
                api_key=test_api_key,
                name="Initial Tenant",
                balance=100.0
            )
            db.add(tenant)
            db.commit()
            print("Initial tenant created.")
        else:
            print("Initial tenant already exists.")
    finally:
        db.close()

if __name__ == "__main__":
    init_db()
