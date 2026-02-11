from pydantic import BaseModel
from typing import Optional

class InitRequest(BaseModel):
    phone: str
    api_key: str # Added in v5.0 for tenant auth
    package_name: Optional[str] = None

class InitResponse(BaseModel):
    deep_link: str

class EchobWebhookPayload(BaseModel):
    event: str
    payload: dict
