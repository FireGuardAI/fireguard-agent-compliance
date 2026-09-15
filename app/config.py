from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    api_title: str = Field(default="FireGuard Compliance Agent")
    api_version: str = Field(default="0.1.0")
    cors_allow_origins: list[str] = Field(default_factory=lambda: ["*"])

    retrieval_service_url: str = Field(default="http://agent-retrieval:8001")
    retrieval_top_k: int = Field(default=5, gt=0)
    retrieval_timeout_seconds: float = Field(default=10.0, gt=0)
    retrieval_max_retries: int = Field(default=3, ge=0)

    gemini_api_key: str
    gemini_model_name: str = Field(default="gemini-1.5-flash")
    gemini_timeout_seconds: float = Field(default=30.0, gt=0)
    gemini_max_retries: int = Field(default=3, ge=0)

    audit_rate_limit: str = Field(default="10/minute")

    log_level: str = Field(default="INFO")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
