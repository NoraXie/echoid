from pydantic import Field
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Project Info
    PROJECT_NAME: str = "EchoID Server"
    VERSION: str = "5.0.0"
    ENV: str = "prod"
    
    # Base Configuration
    HOST_URL: str = Field(..., description="Server A 的公网域名 (e.g., https://api.echoid.com)")
    
    # ECHOB (External WhatsApp Service) Configuration
    ECHOB_API_URL: str = Field(..., description="ECHOB 服务的 API 地址")
    ECHOB_API_KEY: str = Field(..., description="ECHOB 服务的 API Key")
    
    # AI / Offline Factory Configuration
    # Optional: Only required for running offline template generation scripts
    NVIDIA_API_KEY: str = Field("mock-key", description="NVIDIA NIM API Key for template generation")

    # Database & Redis
    DATABASE_URL: str = Field("postgresql://user:password@localhost:5432/echoid", description="数据库连接串")
    REDIS_URL: str = Field("redis://localhost:6379/0", description="Redis 连接串")

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
