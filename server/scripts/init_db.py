import sys
import os

# Adjust path to include the project root
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir))) # waha-server
sys.path.append(project_root)

# Also append echoid/server parent
sys.path.append(os.path.join(project_root, "echoid"))

from server.database import engine, SessionLocal
from server.models import Base, Tenant

def init_db():
    print("Creating tables...")
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    try:
        # Check if test tenant exists
        test_api_key = os.getenv("TEST_TENANT_API_KEY", "test-api-key")
        tenant = db.query(Tenant).filter(Tenant.api_key == test_api_key).first()
        if not tenant:
            print("Creating test tenant...")
            tenant = Tenant(
                api_key=test_api_key,
                name="Test Tenant",
                balance=100.0
            )
            db.add(tenant)
            db.commit()
            print("Test tenant created.")
        else:
            print("Test tenant already exists.")
            # Reset balance for testing if needed
            if tenant.balance <= 0:
                tenant.balance = 100.0
                db.commit()
                print("Reset balance to 100.0")
    finally:
        db.close()

if __name__ == "__main__":
    init_db()
