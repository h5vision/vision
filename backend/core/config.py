"""Environment-backed application settings."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, HttpUrl, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings with no embedded production credentials."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Vision Snapshot Backend"
    api_prefix: str = "/v1"
    vision_environment: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    docs_enabled: bool = True

    rag_lab_base_url: HttpUrl = "http://127.0.0.1:8200"
    rag_lab_token: SecretStr | None = None
    database_url: SecretStr | None = None

    rag_lab_connect_timeout_seconds: float = Field(default=2, gt=0)
    rag_lab_index_accept_timeout_seconds: float = Field(default=8, gt=0, lt=10)
    rag_lab_status_timeout_seconds: float = Field(default=8, gt=0)
    snapshot_forwarding_stale_seconds: int = Field(default=30, gt=0)

    @field_validator("api_prefix")
    @classmethod
    def validate_api_prefix(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        if not normalized.startswith("/") or normalized == "/":
            raise ValueError("api_prefix must be a non-root absolute path")
        return normalized

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("unsupported log level")
        return normalized

    @field_validator("database_url", mode="before")
    @classmethod
    def empty_database_url_is_unset(cls, value):
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("rag_lab_token", mode="before")
    @classmethod
    def empty_token_is_unset(cls, value):
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
