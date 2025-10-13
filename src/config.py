"""Application configuration utilities."""

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    openai_api_key: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("OPENAI_API_KEY", "openai_api_key"),
        description=(
            "API key used to authenticate with OpenAI's APIs. Configure this via environment "
            "variables or a .env file instead of editing the source code."
        ),
    )
    openai_model: str = Field(
        default="gpt-5-mini",
        validation_alias=AliasChoices("OPENAI_MODEL", "openai_model"),
        description="ChatGPT model identifier sent to the OpenAI Responses API.",
    )
    api_auth_token: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("TRIAGE_API_TOKEN", "triage_api_token"),
        description="Shared secret token required in the X-API-Key header.",
    )
    log_db_path: Path = Field(
        default=Path("data/triage_logs.db"),
        validation_alias=AliasChoices("TRIAGE_LOG_DB_PATH", "triage_log_db_path"),
        description="Location of the SQLite database used for request/response logging.",
    )
    uploads_dir: Path = Field(
        default=Path("data/uploads"),
        validation_alias=AliasChoices("TRIAGE_UPLOAD_DIR", "triage_upload_dir"),
        description="Directory where uploaded exam files will be stored.",
    )
    smtp_host: str = Field(
        default="smtp.gmail.com",
        validation_alias=AliasChoices("SMTP_HOST", "smtp_host"),
        description="Hostname of the SMTP server used to dispatch physician summaries.",
    )
    smtp_port: int = Field(
        default=587,
        validation_alias=AliasChoices("SMTP_PORT", "smtp_port"),
        description="Port of the SMTP server used to dispatch physician summaries.",
    )
    smtp_username: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("SMTP_USERNAME", "smtp_username"),
        description="SMTP username (typically the Gmail address) used for authentication.",
    )
    smtp_password: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("SMTP_PASSWORD", "smtp_password"),
        description="SMTP password or app password used for authentication.",
    )
    smtp_sender: Optional[str] = Field(
        default="drathaispreconsulta@gmail.com",
        validation_alias=AliasChoices("SMTP_SENDER", "smtp_sender"),
        description="Email address to use in the From header when emailing physicians.",
    )
    physician_email_recipient: str = Field(
        default="drathaismaltempi@outlook.com",
        validation_alias=AliasChoices("PHYSICIAN_EMAIL_TO", "physician_email_to"),
        description="Destination inbox for automated physician summaries.",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
    )

    @field_validator("log_db_path", mode="before")
    def _expand_log_path(cls, value: Path | str) -> Path:
        """Ensure configured log path is expanded and resolved."""
        path = Path(value).expanduser()
        if not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
        return path

    @field_validator("uploads_dir", mode="before")
    def _prepare_upload_dir(cls, value: Path | str) -> Path:
        """Create the upload directory when needed."""
        path = Path(value).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        return path


@lru_cache()
def get_settings() -> Settings:
    """Return a cached instance of :class:`Settings`."""

    return Settings()


settings = get_settings()
