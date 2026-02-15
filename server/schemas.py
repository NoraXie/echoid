from pydantic import BaseModel
from typing import Optional

class InitRequest(BaseModel):
    api_key: str # Added in v5.0 for tenant auth
    app_name: str # Mandatory for template
    code_challenge: str # Mandatory PKCE support
    package_name: Optional[str] = None # Optional: For Android Deep Link (Intent Scheme)

class InitResponse(BaseModel):
    deep_link: str

class VerifyRequest(BaseModel):
    token: str
    otp: str
    code_verifier: str # Mandatory PKCE support

class EchobWebhookPayload(BaseModel):
    event: str
    payload: dict
