"""Application configuration utilities."""

from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from pydantic import BaseSettings, Field, validator


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    openai_api_key: Optional[str] = Field(
        default=None,
        env="OPENAI_API_KEY",
        description=(
            "API key used to authenticate with OpenAI's APIs. Configure this via environment "
            "variables or a .env file instead of editing the source code."
        ),
    )
    openai_model: str = Field(
        default="gpt-5-mini",
        env="OPENAI_MODEL",
        description="ChatGPT model identifier sent to the OpenAI Responses API.",
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
    smtp_host: str = Field(
        default="smtp.gmail.com",
        env="SMTP_HOST",
        description="Hostname of the SMTP server used to dispatch physician summaries.",
    )
    smtp_port: int = Field(
        default=587,
        env="SMTP_PORT",
        description="Port of the SMTP server used to dispatch physician summaries.",
    )
    smtp_username: Optional[str] = Field(
        default=None,
        env="SMTP_USERNAME",
        description="SMTP username (typically the Gmail address) used for authentication.",
    )
    smtp_password: Optional[str] = Field(
        default=None,
        env="SMTP_PASSWORD",
        description="SMTP password or app password used for authentication.",
    )
    smtp_sender: Optional[str] = Field(
        default="drathaispreconsulta@gmail.com",
        env="SMTP_SENDER",
        description="Email address to use in the From header when emailing physicians.",
    )
    physician_email_recipient: str = Field(
        default="drathaismaltempi@outlook.com",
        env="PHYSICIAN_EMAIL_TO",
        description="Destination inbox for automated physician summaries.",
    )
    cors_allowed_origins: List[str] = Field(
        default_factory=list,
        env="TRIAGE_CORS_ORIGINS",
        description=(
            "Comma separated list of origins allowed to call the public form endpoint."
        ),
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

    @validator("cors_allowed_origins", pre=True)
    def _split_origins(cls, value: Optional[str]):  # type: ignore[override]
        """Allow comma separated origins in environment variables."""

        if not value:
            return []
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache()
def get_settings() -> Settings:
    """Return a cached instance of :class:`Settings`."""

    return Settings()


settings = get_settings()
