from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

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
    BOT_PHONE_NUMBER: str = Field(..., description="WhatsApp Bot Number (e.g. 52155...)")
    
    # Anti-Ban Link Strategy
    LINK_DOMAINS: str = Field("", description="Comma separated list of domains for link rotation (e.g. https://d1.com,https://d2.com)")
    ANDROID_PACKAGE_NAME: str = Field("", description="Android Package Name for Intent URL (e.g. com.example.app)")
    ANDROID_APP_FINGERPRINT: str = Field("", description="SHA256 Fingerprint for App Links (e.g. FA:C6:17:45:...)")
    ANDROID_ASSETLINKS_JSON: str = Field("", description="Raw JSON content for .well-known/assetlinks.json (Overrides single app config)")

    # AI / Offline Factory Configuration
    # Optional: Only required for running offline template generation scripts
    NVIDIA_API_KEY: str = Field("mock-key", description="NVIDIA NIM API Key for template generation")
    NVIDIA_BASE_URL: str = Field("https://integrate.api.nvidia.com/v1", description="NVIDIA NIM Base URL")
    NVIDIA_MODEL: str = Field("meta/llama3-70b-instruct", description="Model name to use")

    # Database & Redis
    DATABASE_URL: str = Field("postgresql://user:password@localhost:5432/echoid", description="数据库连接串")
    REDIS_URL: str = Field("redis://localhost:6379/0", description="Redis 连接串")

    # Time-To-Live (TTL) & Limits Configuration
    SESSION_TTL: int = Field(600, description="Session validity in seconds (default: 10 mins)")
    OTP_TTL: int = Field(300, description="OTP validity in seconds (default: 5 mins)")
    SHORT_LINK_TTL: int = Field(300, description="Short link validity in seconds (default: 5 mins)")
    
    # Rate Limits
    RATE_LIMIT_INIT: int = Field(5, description="Max init requests per period")
    RATE_LIMIT_INIT_PERIOD: int = Field(60, description="Init rate limit period in seconds")
    RATE_LIMIT_WEBHOOK: int = Field(10, description="Max webhook requests per period")
    RATE_LIMIT_WEBHOOK_PERIOD: int = Field(60, description="Webhook rate limit period in seconds")


    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore"
    )

settings = Settings()
