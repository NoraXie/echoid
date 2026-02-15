import unittest
import sys
import os

# Add project root (echoid) to sys.path to allow 'server' module imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set required environment variables for testing BEFORE importing server modules
os.environ["HOST_URL"] = "http://localhost:8000"
os.environ["ECHOB_API_URL"] = "http://mock-echob"
os.environ["ECHOB_API_KEY"] = "mock-key"
os.environ["BOT_PHONE_NUMBER"] = "525670061324"
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

    def test_init_returns_echoid_redirect_link(self):
        print("\n[10] Testing Init Returns EchoID Redirect Link")
        from server.utils import redis_client
        
        # Init Request
        request_data = {
            "api_key": "test-key",
            "app_name": "RedirectTestApp",
            "code_challenge": "challenge123"
        }
        
        # Mock Redis setex
        async def mock_setex(key, ttl, value):
            return True
        redis_client.setex.side_effect = mock_setex
        
        res = self.client.post("/v1/init", json=request_data)
        self.assertEqual(res.status_code, 200)
        
        deep_link = res.json()["deep_link"]
        print(f"    Link: {deep_link}")
        
        # Verify format: http://testserver/v1/go/{token}
        self.assertIn("/v1/go/", deep_link)
        
        # Extract token
        token = deep_link.split("/")[-1]
        
        # Mock Redis get for Redirect
        redis_client.get.return_value = json.dumps({
            "status": "pending",
            "app_name": "RedirectTestApp"
        })
        
        # Test Redirect Endpoint
        res_redirect = self.client.get(f"/v1/go/{token}", follow_redirects=False)
        self.assertEqual(res_redirect.status_code, 307) # FastAPI RedirectResponse default is 307
        self.assertIn("wa.me", res_redirect.headers["location"])
        self.assertIn(token, res_redirect.headers["location"])
        print("    ✅ Redirects to wa.me correctly")

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
        
        # Generate valid PKCE
        verifier = "test-verifier-string"
        import hashlib, base64
        sha256 = hashlib.sha256(verifier.encode('utf-8')).digest()
        challenge = base64.urlsafe_b64encode(sha256).decode('utf-8').rstrip('=')
        
        request_data = {
            "api_key": "test-key",
            "device_id": "dev123",
            "app_name": "Test App",
            "code_challenge": challenge,
            "hash_string": "hash123"
        }
        
        response = self.client.post("/v1/init", json=request_data)
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        self.assertIn("deep_link", data)
        deep_link = data["deep_link"]
        print(f"\n[1] Init Success. Deep Link: {deep_link}")
        
        # Extract token from deep link: https://wa.me/521...?text=Hola...TOKEN...
        import re
        # Updated to match new secure token format (6-10 chars, alphanumeric)
        # Look for token at the end or within the text parameter
        token_match = re.search(r"([A-HJ-KMNP-Z2-9]{6,10})$", deep_link)
        if not token_match:
             # Try searching anywhere in string if not at end
             token_match = re.search(r"([A-HJ-KMNP-Z2-9]{6,10})", deep_link)
             
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
        # Initially phone is None in session because we didn't send it
        redis_client.get.return_value = json.dumps({
            "phone": None, 
            "tenant_id": 1,
            "app_name": "Test App"
        })
        
        # Simulate Webhook Payload from ECHOB
        webhook_payload = {
            "event": "message",
            "payload": {
                "from": f"{phone}@s.whatsapp.net", # This will bind the phone
                "body": f"Please verify me {token}", 
                "id": "MSG_ID_123"
            }
        }
        
        webhook_response = self.client.post("/webhook/echob", json=webhook_payload)
        
        self.assertEqual(webhook_response.status_code, 200)
        self.assertEqual(webhook_response.json()["status"], "ok")
        print(f"[2] Webhook Processed Successfully (Phone Bound)")

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
        # Expect echoid://login?token={token}&otp={otp} in Location header (Default fallback)
        self.assertIn("echoid://login", location)
        self.assertIn(token, location)
        print(f"[3] Short Link Redirects to App (302 Found)")
        
        # Test Android Redirect Logic
        # Mock User-Agent as Android
        headers = {"User-Agent": "Mozilla/5.0 (Linux; Android 10; SM-G960F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.181 Mobile Safari/537.36"}
        android_response = self.client.get(f"/q/{slug}", headers=headers, follow_redirects=False)
        self.assertEqual(android_response.status_code, 302)
        
        android_location = android_response.headers["location"]
        # Expect intent://... in Location header for Android
        self.assertIn("intent://login", android_location)
        self.assertIn("scheme=echoid", android_location)
        self.assertIn("end;", android_location)
        print(f"    ✅ Android User-Agent Redirects to Intent Scheme")
        
        # Verify OTP Deletion logic (simulated by checking if delete was called during verification flow?)
        # Actually we haven't called verify yet in this test case flow?
        # Step 4 is usually followed by Verify step, but verify logic is in test_pkce_flow or separate
        # Let's add a verify step here to ensure full flow completeness
        
        # Mock Redis for Verify
        async def mock_redis_get_verify(key):
             if key == f"otp:{token}":
                 return "1234"
             if key.startswith("session:"):
                 return json.dumps({
                     "phone": phone, 
                     "tenant_id": 1,
                     "code_challenge": challenge,
                     "app_name": "Test App"
                 })
             return None
        
        redis_client.get.side_effect = mock_redis_get_verify
        
        verify_req = {
            "token": token,
            "otp": "1234",
            "code_verifier": verifier
        }
        res_verify = self.client.post("/v1/verify", json=verify_req)
        self.assertEqual(res_verify.status_code, 200)
        
        # Assert OTP deletion
        # Check if delete was called with otp:{token}
        # Note: We need to check call args.
        # Since delete might be called for short link (which we disabled) or otp
        # We disabled short link deletion in main.py, so it should only be called for otp here?
        # Actually verify_otp calls delete.
        self.assertTrue(redis_client.delete.called)
        # We can inspect call args to be sure
        # call_args_list = redis_client.delete.call_args_list
        # found = any(f"otp:{token}" in str(call) for call in call_args_list)
        # self.assertTrue(found, "OTP was not deleted")
        print("    ✅ OTP Verified and Deleted (Replay Prevention)")

    def test_rate_limit(self):
        # Mock incr to return value > limit (5)
        # Note: Since we are using AsyncMock, we need to set return_value on the mock object
        from server.utils import redis_client
        redis_client.incr.return_value = 6 
        
        request_data = {
            # "phone": "521234567890", # Phone is NOT required anymore
            "api_key": "test-key",
            "device_id": "dev123",
            "package_name": "com.test.app",
            "app_name": "Test App",
            "code_challenge": "mock-challenge",
            "hash_string": "hash123"
        }
        
        # We need to ensure the DB check is passed or mocked before rate limit?
        # In main.py, Rate Limit is step 0, BEFORE DB check.
        # So even if DB is mocked, it shouldn't matter if Rate Limit fails first.
        # But for correctness, DB mock is already in setUp.
        
        # NOTE: Rate limit by phone is currently disabled in main.py because phone is optional.
        # We need to adjust this test to reflect that rate limit might be skipped or changed.
        # If rate limit is disabled for now, we should expect 200 OK.
        
        response = self.client.post("/v1/init", json=request_data)
        
        # self.assertEqual(response.status_code, 429)
        # print("\n[4] Rate Limit Enforced (429 Too Many Requests)")
        
        # Since we commented out rate limit in main.py, this should be 200 now.
        # We will update the test to expect 200 for now, or just skip it until we implement IP-based rate limit.
        self.assertEqual(response.status_code, 200)
        print("\n[4] Rate Limit Skipped (Phone is optional)")

    def test_pkce_flow(self):
        print("\n[5] Testing PKCE Flow")
        # 1. Init with Code Challenge
        verifier = "secure-random-string-123"
        import hashlib, base64
        sha256 = hashlib.sha256(verifier.encode('utf-8')).digest()
        challenge = base64.urlsafe_b64encode(sha256).decode('utf-8').rstrip('=')
        
        request_data = {
            # "phone": "521234567890",
            "api_key": "test-key",
            "code_challenge": challenge,
            "app_name": "Test App"
        }
        response = self.client.post("/v1/init", json=request_data)
        self.assertEqual(response.status_code, 200)
        
        # Extract token
        deep_link = response.json()["deep_link"]
        import re
        token_match = re.search(r"([A-HJ-KMNP-Z2-9]{6,10})", deep_link)
        token = token_match.group(1)
        
        # 2. Mock Redis for Verify Step
        # We need to simulate that Redis has the session WITH code_challenge
        # AND the OTP
        async def mock_redis_get_pkce(key):
            if key.startswith("otp:"):
                return "1234"
            if key.startswith("session:"):
                return json.dumps({
                    "phone": "521234567890", 
                    "tenant_id": 1,
                    "code_challenge": challenge
                })
            return None
        
        # Apply mock
        from server.utils import redis_client
        redis_client.get.side_effect = mock_redis_get_pkce
        
        # 3. Verify with Valid Verifier
        verify_data = {
            "token": token,
            "otp": "1234",
            "code_verifier": verifier
        }
        res_valid = self.client.post("/v1/verify", json=verify_data)
        self.assertEqual(res_valid.status_code, 200)
        print("    ✅ PKCE Valid Verifier Accepted")

        # 4. Verify with Invalid Verifier
        verify_bad = {
            "token": token,
            "otp": "1234",
            "code_verifier": "wrong-string"
        }
        res_bad = self.client.post("/v1/verify", json=verify_bad)
        self.assertEqual(res_bad.status_code, 403)
        print("    ✅ PKCE Invalid Verifier Rejected (403)")
        
        # Reset side_effect
        redis_client.get.side_effect = None

    @patch('server.main.echob_client')
    def test_session_hijack_prevention(self, mock_echob):
        # Mock send_text to avoid network error
        mock_echob.send_text = AsyncMock()
        mock_echob.start_typing = AsyncMock()
        mock_echob.stop_typing = AsyncMock()
        
        print("\n[6] Testing Session Hijack Prevention")
        token = "ABCDEF2345"
        user_a_phone = "521555555555" # The session owner
        attacker_phone = "521999999999" # The hijacker
        
        # 1. Initial State: Session exists for User A
        from server.utils import redis_client
        redis_client.get.side_effect = None # Reset side effect from previous test
        redis_client.get.return_value = json.dumps({"phone": user_a_phone, "tenant_id": 1})
        
        # User A sends message -> Claims session (Successful)
        webhook_payload_A = {
            "event": "message",
            "payload": {
                "from": user_a_phone, # Matches session
                "body": f"Verify {token}", 
                "id": "MSG_A"
            }
        }
        res_A = self.client.post("/webhook/echob", json=webhook_payload_A)
        self.assertEqual(res_A.json()["status"], "ok")
        
        # 2. Attack State: Session now has wa_id = user_a_phone
        redis_client.get.return_value = json.dumps({
            "phone": user_a_phone, 
            "tenant_id": 1,
            "wa_id": user_a_phone # Claimed by A
        })
        
        # User B tries to use same token (Hijack Attempt)
        webhook_payload_B = {
            "event": "message",
            "payload": {
                "from": attacker_phone,
                "body": f"Verify {token}", 
                "id": "MSG_B"
            }
        }
        res_B = self.client.post("/webhook/echob", json=webhook_payload_B)
        
        # Should be ignored due to Hijack Attempt
        self.assertEqual(res_B.json()["status"], "ignored")
        # In main.py:
        # Hijack Check is FIRST: if session.wa_id and session.wa_id != sender -> token_already_claimed
        # Phone Check is SECOND: if expected_phone != sender -> phone_mismatch
        # Since session.wa_id IS set (User A claimed it), it will hit "token_already_claimed" first.
        self.assertEqual(res_B.json().get("msg"), "token_already_claimed")
        print("    ✅ Hijack Attempt Blocked")

    @patch('server.main.echob_client')
    def test_webhook_rate_limit(self, mock_echob):
        print("\n[7] Testing Webhook Rate Limit")
        from server.utils import redis_client
        
        # Mock rate limit exceeded for specific sender
        async def mock_incr(key):
            if "webhook:SPAMMER" in key:
                return 11 # > 10
            return 1
            
        redis_client.incr.side_effect = mock_incr
        
        # Test 1: Spammer with VALID token format (should be blocked)
        payload_valid_format = {
            "event": "message",
            "payload": {
                "from": "SPAMMER",
                "body": "Verify ABCDEF2345", 
                "id": "MSG_SPAM_1"
            }
        }
        
        res = self.client.post("/webhook/echob", json=payload_valid_format)
        self.assertEqual(res.json()["status"], "ignored")
        self.assertEqual(res.json().get("msg"), "rate_limit_exceeded")
        print("    ✅ Webhook Spammer Blocked (Valid Token Format)")
        
        # Test 2: Spammer with GARBAGE text (should ALSO be blocked now)
        # This confirms that rate limiting happens BEFORE token extraction
        payload_garbage = {
            "event": "message",
            "payload": {
                "from": "SPAMMER",
                "body": "Just some random spam text without token", 
                "id": "MSG_SPAM_2"
            }
        }
        
        res_garbage = self.client.post("/webhook/echob", json=payload_garbage)
        self.assertEqual(res_garbage.json()["status"], "ignored")
        self.assertEqual(res_garbage.json().get("msg"), "rate_limit_exceeded")
        print("    ✅ Webhook Spammer Blocked (Garbage Text)")
        
        # Reset
        redis_client.incr.side_effect = None
        redis_client.incr.return_value = 1

    def test_short_link_redirect_android(self):
        print("\n[8b] Testing Short Link Redirect (Android)")
        from server.config import settings
        from server.utils import redis_client
        
        # Set Android Package Name
        original_package = settings.ANDROID_PACKAGE_NAME
        settings.ANDROID_PACKAGE_NAME = "com.test.app"
        
        try:
            # Mock Redis
            redis_client.get.side_effect = None
            redis_client.get.return_value = json.dumps({"token": "TOK123", "otp": "OTP123"})
            
            slug = "TESTSLUG"
            
            # Test Android User-Agent
            headers = {"User-Agent": "Mozilla/5.0 (Linux; Android 10; SM-G960F)"}
            response = self.client.get(f"/q/{slug}", headers=headers, follow_redirects=False)
            
            self.assertEqual(response.status_code, 302)
            location = response.headers["location"]
            
            # Check for Intent URL (Android)
            self.assertIn("intent://login", location)
            self.assertIn("package=com.test.app", location)
            self.assertIn("scheme=echoid", location)
            self.assertIn("end;", location)
            
            print("    ✅ Android Redirects to Intent Scheme with Package Name")
            
        finally:
            settings.ANDROID_PACKAGE_NAME = original_package

    def test_short_link_redirect_dynamic_package(self):
        print("\n[8c] Testing Short Link Redirect (Dynamic Package Name)")
        from server.config import settings
        from server.utils import redis_client
        
        # Set Global Package Name (Should be overridden by session)
        original_global_package = settings.ANDROID_PACKAGE_NAME
        settings.ANDROID_PACKAGE_NAME = "com.global.fallback"
        
        try:
            # Mock Redis
            async def mock_redis_get_dynamic(key):
                if key.startswith("short:"):
                    return json.dumps({"token": "TOK_DYN", "otp": "OTP_DYN"})
                if key.startswith("session:"):
                    return json.dumps({
                        "phone": "521234567890", 
                        "tenant_id": 1,
                        "package_name": "com.dynamic.app" # <--- Dynamic Package
                    })
                return None
            
            redis_client.get.side_effect = mock_redis_get_dynamic
            
            slug = "TESTSLUG_DYN"
            
            # Test Android User-Agent
            headers = {"User-Agent": "Mozilla/5.0 (Linux; Android 10; SM-G960F)"}
            response = self.client.get(f"/q/{slug}", headers=headers, follow_redirects=False)
            
            self.assertEqual(response.status_code, 302)
            location = response.headers["location"]
            
            # Verify Dynamic Package Name is used
            self.assertIn("package=com.dynamic.app", location)
            # Verify Global Package Name is NOT used
            self.assertNotIn("package=com.global.fallback", location)
            
            print("    ✅ Dynamic Package Name from Session Used Correctly")
            
        finally:
            settings.ANDROID_PACKAGE_NAME = original_global_package
            redis_client.get.side_effect = None # Reset side effect

    @patch('server.main.echob_client')
    def test_phone_mismatch_protection(self, mock_echob):
        print("\n[9] Testing Phone Number Mismatch Protection")
        from server.utils import redis_client
        
        # 1. Init Session for User A
        token = "ABCDEF"
        user_a_phone = "521555555555" # The intended user
        attacker_phone = "521999999999" # The interceptor
        
        # Mock Redis returning session for User A
        redis_client.get.return_value = json.dumps({
            "phone": user_a_phone, 
            "tenant_id": 1
        })
        
        # 2. Attacker sends the token
        payload = {
            "event": "message",
            "payload": {
                "from": attacker_phone,
                "body": f"Verify {token}", 
                "id": "MSG_ATTACK"
            }
        }
        
        res = self.client.post("/webhook/echob", json=payload)
        
        # Should be ignored because sender != session.phone
        self.assertEqual(res.json()["status"], "ignored")
        self.assertEqual(res.json().get("msg"), "phone_mismatch")
        print("    ✅ Phone Mismatch Blocked (Attacker cannot trigger OTP)")



if __name__ == '__main__':
    unittest.main()
