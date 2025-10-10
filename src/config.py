"""Application configuration utilities."""

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import BaseSettings, Field, validator


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    openai_api_key: Optional[str] = Field(
        default=None,
        env="OPENAI_API_KEY",
        description="API key used to authenticate with OpenAI's APIs.",
    )
    api_auth_token: Optional[str] = Field(
        default=None,
        env="TRIAGE_API_TOKEN",
        description="Shared secret token required in the X-API-Key header.",
    )
    log_db_path: Path = Field(
        default=Path("data/triage_logs.db"),
        env="TRIAGE_LOG_DB_PATH",
        description="Location of the SQLite database used for request/response logging.",
    )
    uploads_dir: Path = Field(
        default=Path("data/uploads"),
        env="TRIAGE_UPLOAD_DIR",
        description="Directory where uploaded exam files will be stored.",
    )

    class Config:
        env_file = ".env"
        case_sensitive = False

    @validator("log_db_path", pre=True)
    def _expand_log_path(cls, value: Path) -> Path:  # type: ignore[override]
        """Ensure configured log path is expanded and resolved."""
        path = Path(value).expanduser()
        if not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
        return path

    @validator("uploads_dir", pre=True)
    def _prepare_upload_dir(cls, value: Path) -> Path:  # type: ignore[override]
        """Create the upload directory when needed."""
        path = Path(value).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        return path


@lru_cache()
def get_settings() -> Settings:
    """Return a cached instance of :class:`Settings`."""

    return Settings()


settings = get_settings()
