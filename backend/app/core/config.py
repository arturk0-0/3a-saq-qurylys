from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../.env", extra="ignore")

    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    firebase_enabled: bool = False
    firebase_project_id: str = Field(default="saq-qurylys", min_length=1, max_length=100)
    firebase_credentials_path: Path | None = None
    firebase_storage_bucket: str = ""
    firebase_demo_only: bool = True

    @field_validator("firebase_credentials_path", mode="before")
    @classmethod
    def empty_credentials_path(cls, value):
        return None if value == "" else value

    @field_validator("cors_origins")
    @classmethod
    def validate_origins(cls, origins: list[str]) -> list[str]:
        from urllib.parse import urlsplit

        for origin in origins:
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path
                or parsed.query
                or parsed.fragment
                or "*" in origin
            ):
                raise ValueError("CORS origins must be explicit HTTP(S) origins without paths")
            # Accessing port also rejects invalid port numbers.
            _ = parsed.port
        return origins
