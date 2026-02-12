import unittest
import sys
import os

# Add project root (echoid) to sys.path to allow 'server' module imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set required environment variables for testing BEFORE importing server modules
os.environ["HOST_URL"] = "http://localhost:8000"
os.environ["ECHOB_API_URL"] = "http://mock-echob"
os.environ["ECHOB_API_KEY"] = "mock-key"
os.environ["DATABASE_URL"] = "sqlite:///./test.db"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"

from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
import json

# Mock redis before importing main
with patch('redis.asyncio.from_url') as mock_redis_factory:
    mock_redis_instance = AsyncMock()
    mock_redis_factory.return_value = mock_redis_instance
    
    # Mock database
    with patch('server.database.SessionLocal') as mock_session_local:
        from server.main import app, get_db
        from server.utils import redis_client
        from server.models import Tenant

class TestEchoIDFlow(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        
        # Reset mocks
        redis_client.setex = AsyncMock()
        redis_client.get = AsyncMock()
        redis_client.setnx = AsyncMock(return_value=True) # Default acquire lock success
        redis_client.srandmember = AsyncMock(return_value="Code: {otp} Link: {link}") # Mock template
        redis_client.incr = AsyncMock(return_value=1) # Default rate limit count
        redis_client.expire = AsyncMock()

        # Mock DB Session
        self.mock_db = MagicMock()
        self.mock_tenant = Tenant(id=1, api_key="test-key", balance=10.0, name="TestApp")
        self.mock_db.query.return_value.filter.return_value.first.return_value = self.mock_tenant
        
        # Override get_db dependency
        def override_get_db():
            yield self.mock_db
        app.dependency_overrides[get_db] = override_get_db

    @patch('server.main.echob_client')
    @patch('server.main.SessionLocal') # For background task
    def test_full_flow(self, mock_session_local, mock_echob):
        # Setup ECHOB client mocks
        mock_echob.start_typing = AsyncMock()
        mock_echob.send_text = AsyncMock()
        mock_echob.stop_typing = AsyncMock()
        
        # Setup Background Task DB Mock
        mock_bg_db = MagicMock()
        mock_session_local.return_value = mock_bg_db
        mock_bg_db.query.return_value.filter.return_value.first.return_value = self.mock_tenant

        # ==========================================
        # Step 1: Init Verification (App -> Server A)
        # ==========================================
        phone = "521234567890"
        request_data = {
            "phone": phone,
            "api_key": "test-key",
            "device_id": "dev123",
            "package_name": "com.test.app",
            "hash_string": "hash123"
        }
        
        response = self.client.post("/v1/init", json=request_data)
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        self.assertIn("deep_link", data)
        deep_link = data["deep_link"]
        print(f"\n[1] Init Success. Deep Link: {deep_link}")
        
        # Extract token from deep link: https://wa.me/521...?text=LOGIN-XXXXX or text=TOKEN
        import re
        # Updated to match new secure token format (6-10 chars, alphanumeric)
        token_match = re.search(r"text=([A-HJ-KMNP-Z2-9]{6,10})", deep_link)
        self.assertTrue(token_match, f"Deep link {deep_link} does not contain valid token")
        token = token_match.group(1)
        print(f"    Token: {token}")
        
        # Verify Redis was called to save session
        self.assertTrue(redis_client.setex.called)
        
        # ==========================================
        # Step 2: Simulate User Sending Message (Server B -> Server A)
        # ==========================================
        
        # Prepare Redis to return the session when queried
        # It returns JSON string now
        redis_client.get.return_value = json.dumps({"phone": phone, "tenant_id": 1})
        
        # Simulate Webhook Payload from ECHOB
        webhook_payload = {
            "event": "message",
            "payload": {
                "from": "521555555555@s.whatsapp.net",
                "body": f"Please verify me {token}", 
                "id": "MSG_ID_123"
            }
        }
        
        webhook_response = self.client.post("/webhook/echob", json=webhook_payload)
        
        self.assertEqual(webhook_response.status_code, 200)
        self.assertEqual(webhook_response.json()["status"], "ok")
        print(f"[2] Webhook Processed Successfully")

        # ==========================================
        # Step 3: Verify ECHOB Interaction
        # ==========================================
        
        # 1. Check typing started
        mock_echob.start_typing.assert_called_once()
        print("    ✅ Typing indicator started")
        
        # 2. Check message sent
        mock_echob.send_text.assert_called_once()
        sent_text = mock_echob.send_text.call_args[0][2] # args: (instance, phone, text)
        print(f"    ✅ Message sent to user:\n---\n{sent_text}\n---")
        
        # Verify the message contains a link (Short Link)
        import re
        link_match = re.search(r"(http://[^ ]+/q/[a-zA-Z0-9_-]+)", sent_text)
        self.assertTrue(link_match, "Short link not found in message")
        short_link_url = link_match.group(1)
        print(f"    ✅ Found Short Link: {short_link_url}")
        
        # Extract slug
        slug = short_link_url.split("/")[-1]

        # Mock Redis response for the short link lookup
        # The handler expects {"token": ..., "otp": ...}
        redis_client.get.return_value = json.dumps({"token": token, "otp": "1234"})

        # ==========================================
        # Step 4: Verify Short Link Redirect (User Click -> Browser -> App)
        # ==========================================
        # Test the /q/{slug} endpoint
        short_response = self.client.get(f"/q/{slug}", follow_redirects=False)
        self.assertEqual(short_response.status_code, 302)
        location = short_response.headers["location"]
        print(f"[3] Short Link Redirects to: {location}")
        
        # Expect echoid://login?token={token}&otp={otp}
        self.assertIn("echoid://login", location)
        self.assertIn(token, location)
        print("    ✅ Redirects to Custom Scheme correctly")

    def test_rate_limit(self):
        # Mock incr to return value > limit (5)
        # Note: Since we are using AsyncMock, we need to set return_value on the mock object
        from server.utils import redis_client
        redis_client.incr.return_value = 6 
        
        request_data = {
            "phone": "521234567890",
            "api_key": "test-key",
            "device_id": "dev123",
            "package_name": "com.test.app",
            "hash_string": "hash123"
        }
        
        # We need to ensure the DB check is passed or mocked before rate limit?
        # In main.py, Rate Limit is step 0, BEFORE DB check.
        # So even if DB is mocked, it shouldn't matter if Rate Limit fails first.
        # But for correctness, DB mock is already in setUp.
        
        response = self.client.post("/v1/init", json=request_data)
        
        self.assertEqual(response.status_code, 429)
        print("\n[4] Rate Limit Enforced (429 Too Many Requests)")

if __name__ == '__main__':
    unittest.main()
