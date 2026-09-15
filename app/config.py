"""Centralized, type-safe application configuration.

Same pattern as fireguard-vector-store/src/config.py and
fireguard-agent-retrieval/app/config.py — one validated Settings object.

NOTE: gemini_api_key has NO default — Pydantic will raise a validation
error at startup if it's missing from .env, which is exactly the
behavior we want (fail loudly and immediately, not on the first
request that happens to hit the compliance engine).
"""
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # API metadata
    api_title: str = Field(default="FireGuard Compliance Agent")
    api_version: str = Field(default="0.1.0")
    cors_allow_origins: list[str] = Field(default_factory=lambda: ["*"])

    # Retrieval agent connection (Step 2) — service name on the shared
    # fireguard-net Docker network, not localhost
    retrieval_service_url: str = Field(default="http://agent-retrieval:8001")
    retrieval_top_k: int = Field(default=5, gt=0)
    retrieval_timeout_seconds: float = Field(default=10.0, gt=0)

    # Gemini LLM connection (Step 3) — required, no default
    gemini_api_key: str
    gemini_model_name: str = Field(default="gemini-1.5-flash")
    gemini_timeout_seconds: float = Field(default=30.0, gt=0)
    gemini_max_retries: int = Field(default=3, ge=0)

    # Observability
    log_level: str = Field(default="INFO")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
