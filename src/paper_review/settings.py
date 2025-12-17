from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from pydantic import Field
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILES = [
    str(Path(__file__).resolve().parents[2] / ".env"),
    ".env",
]
_DEFAULT_UPLOAD_DIR = Path(__file__).resolve().parents[2] / "data" / "uploads"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILES, env_file_encoding="utf-8", extra="ignore")

    database_url: str = Field(
        default="postgresql+psycopg2://postgres:postgres@localhost:5432/paper_review",
        alias="DATABASE_URL",
    )

    api_key: str | None = Field(default=None, alias="API_KEY")

    web_username: str | None = Field(default=None, alias="WEB_USERNAME")
    web_password: str | None = Field(default=None, alias="WEB_PASSWORD")
    session_secret: str | None = Field(default=None, alias="SESSION_SECRET")
    cookie_https_only: bool = Field(default=False, alias="COOKIE_HTTPS_ONLY")
    upload_dir: Path = Field(default=_DEFAULT_UPLOAD_DIR, alias="UPLOAD_DIR")
    upload_backend: str = Field(default="local", alias="UPLOAD_BACKEND")

    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4.1-mini", alias="OPENAI_MODEL")
    openai_delete_files: bool = Field(default=True, alias="OPENAI_DELETE_FILES")
    openai_timeout_seconds: int = Field(default=600, alias="OPENAI_TIMEOUT_SECONDS")

    embeddings_provider: str = Field(default="local", alias="EMBEDDINGS_PROVIDER")
    embeddings_normalize: bool = Field(default=True, alias="EMBEDDINGS_NORMALIZE")

    local_embed_model: str = Field(default="intfloat/e5-base-v2", alias="LOCAL_EMBED_MODEL")
    local_embed_device: str | None = Field(default=None, alias="LOCAL_EMBED_DEVICE")
    local_embed_batch_size: int = Field(default=32, alias="LOCAL_EMBED_BATCH_SIZE")

    openai_embed_model: str = Field(default="text-embedding-3-large", alias="OPENAI_EMBED_MODEL")
    openai_embed_batch_size: int = Field(default=96, alias="OPENAI_EMBED_BATCH_SIZE")

    server_base_url: str = Field(default="http://127.0.0.1:8000", alias="SERVER_BASE_URL")
    server_api_key: str | None = Field(default=None, alias="SERVER_API_KEY")

    recommender_query_llm_provider: str = Field(default="local", alias="RECOMMENDER_QUERY_LLM_PROVIDER")
    recommender_decider_llm_provider: str = Field(default="openai", alias="RECOMMENDER_DECIDER_LLM_PROVIDER")

    local_llm_model: str = Field(default="gpt-oss-20b", alias="LOCAL_LLM_MODEL")
    local_llm_device_map: str = Field(default="auto", alias="LOCAL_LLM_DEVICE_MAP")
    local_llm_torch_dtype: str = Field(default="auto", alias="LOCAL_LLM_TORCH_DTYPE")
    local_llm_max_new_tokens: int = Field(default=256, alias="LOCAL_LLM_MAX_NEW_TOKENS")
    local_llm_temperature: float = Field(default=0.2, alias="LOCAL_LLM_TEMPERATURE")
    local_llm_top_p: float = Field(default=0.95, alias="LOCAL_LLM_TOP_P")
    local_llm_trust_remote_code: bool = Field(default=False, alias="LOCAL_LLM_TRUST_REMOTE_CODE")

    ollama_base_url: str = Field(default="http://127.0.0.1:11434", alias="OLLAMA_BASE_URL")
    ollama_timeout_seconds: int = Field(default=120, alias="OLLAMA_TIMEOUT_SECONDS")

    google_client_id: str | None = Field(default=None, alias="GOOGLE_CLIENT_ID")
    google_client_secret: str | None = Field(default=None, alias="GOOGLE_CLIENT_SECRET")
    google_refresh_token: str | None = Field(default=None, alias="GOOGLE_REFRESH_TOKEN")
    google_service_account_file: str | None = Field(default=None, alias="GOOGLE_SERVICE_ACCOUNT_FILE")
    google_drive_scope: str = Field(
        default="https://www.googleapis.com/auth/drive.readonly", alias="GOOGLE_DRIVE_SCOPE"
    )
    google_drive_upload_folder_id: str | None = Field(default=None, alias="GOOGLE_DRIVE_UPLOAD_FOLDER_ID")

    semantic_scholar_api_key: str | None = Field(default=None, alias="SEMANTIC_SCHOLAR_API_KEY")

    worker_poll_seconds: int = Field(default=3, alias="WORKER_POLL_SECONDS")
    max_pdf_mb: int = Field(default=50, alias="MAX_PDF_MB")

    @property
    def web_auth_enabled(self) -> bool:
        return bool(self.web_username and self.web_password)

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalize_database_url(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            return v
        url = v.strip()
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://") :]
        if url.startswith("postgresql+psycopg://"):
            url = "postgresql+psycopg2://" + url[len("postgresql+psycopg://") :]
        if url.startswith("postgresql://") and not url.startswith("postgresql+"):
            url = "postgresql+psycopg2://" + url[len("postgresql://") :]

        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if "supabase" in host:
            query = dict(parse_qsl(parsed.query, keep_blank_values=True))
            if "sslmode" not in query:
                query["sslmode"] = "require"
                parsed = parsed._replace(query=urlencode(query))
                url = urlunparse(parsed)
        return url


settings = Settings()
