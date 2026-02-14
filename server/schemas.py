from pydantic import BaseModel
from typing import Optional

class InitRequest(BaseModel):
    phone: str
    api_key: str # Added in v5.0 for tenant auth
    package_name: Optional[str] = None
    code_challenge: Optional[str] = None # PKCE support

class InitResponse(BaseModel):
    deep_link: str

class VerifyRequest(BaseModel):
    token: str
    otp: str
    code_verifier: Optional[str] = None # PKCE support

class EchobWebhookPayload(BaseModel):
    event: str
    payload: dict
