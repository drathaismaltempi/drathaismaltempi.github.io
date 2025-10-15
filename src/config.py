"""Application configuration utilities."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Iterable, List, Optional

from pydantic import BaseSettings, Field, validator


def _safe_json_loads(value):
    """Attempt JSON decoding while tolerating blank or malformed strings."""

    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return value

    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return value


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

    class Config(BaseSettings.Config):
        env_file = ".env"
        case_sensitive = False

        @classmethod
        def parse_env_var(cls, field_name, raw_value):
            """Normalize the CORS allow-list regardless of value format."""

            if field_name == "cors_allowed_origins":
                return _coerce_origins(raw_value)

            return raw_value

        json_loads = staticmethod(_safe_json_loads)

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
    def _split_origins(cls, value):  # type: ignore[override]
        """Coerce any provided origins collection into a clean list of strings."""

        return _coerce_origins(value)


def _coerce_origins(value) -> List[str]:
    """Return a sanitized list of CORS origins for any supported input."""

    if value is None:
        return []

    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return []

        if candidate.lower() in {"null", "none"}:
            return []

        parsed = None
        if candidate[0] in "[{\"":
            parsed = _safe_json_loads(candidate)

        if isinstance(parsed, str):
            candidate = parsed.strip()
            if not candidate:
                return []
            return [candidate]

        if isinstance(parsed, Iterable) and not isinstance(parsed, (str, bytes, bytearray)):
            cleaned = []
            for origin in parsed:
                if origin is None:
                    continue
                text = str(origin).strip()
                if text:
                    cleaned.append(text)
            return cleaned

        origins = []
        for origin in candidate.split(","):
            text = origin.strip()
            if text and text.lower() not in {"null", "none"}:
                origins.append(text)
        return origins

    if isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray)):
        cleaned = []
        for origin in value:
            if origin is None:
                continue
            text = str(origin).strip()
            if text and text.lower() not in {"null", "none"}:
                cleaned.append(text)
        return cleaned

    return []


@lru_cache()
def get_settings() -> Settings:
    """Return a cached instance of :class:`Settings`."""

    return Settings()


settings = get_settings()
