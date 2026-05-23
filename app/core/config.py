from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # ── Auth ──────────────────────────────────────────────────────────────────
    secret_key: str = Field(default="change-me-in-production-32-chars-min", min_length=16)
    allowed_origins: list[str] = Field(default=["http://localhost:5173", "http://localhost:3000"])

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = "sqlite+aiosqlite:///./rag_studio.db"

    # ── Azure OpenAI ──────────────────────────────────────────────────────────
    azure_openai_endpoint:    str = ""
    azure_openai_api_key:     str = ""
    azure_openai_api_version: str = "2024-08-01-preview"

    azure_openai_deployment_gpt4o:       str = "gpt-4o"
    azure_openai_deployment_gpt4o_mini:  str = "gpt-4o-mini"
    azure_openai_deployment_embedding:   str = "text-embedding-3-large"

    # ── Direct OpenAI fallback ────────────────────────────────────────────────
    openai_api_key: str = ""

    # ── Redis + Celery ────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379"

    # When true, ingestion is queued to Celery; otherwise it runs inline in the
    # web request. Default is False because preprod/prod typically don't have a
    # dedicated worker service yet — keeping uploads inline ensures they actually
    # complete instead of sitting forever in 'queued' status.
    enable_celery: bool = False

    @property
    def celery_broker_url(self) -> str:
        return self.redis_url

    @property
    def celery_result_backend(self) -> str:
        return self.redis_url

    # ── ChromaDB ──────────────────────────────────────────────────────────────
    chroma_persist_dir: str = "./chroma_db"

    # ── App ───────────────────────────────────────────────────────────────────
    log_level:   str = "INFO"
    environment: str = "development"

    # ── Admin ─────────────────────────────────────────────────────────────────
    # Users whose email matches this are automatically made admin on first login
    admin_email: str = "kartikanand0012@gmail.com"

    # ── Chunking ──────────────────────────────────────────────────────────────
    chunk_size:    int = 500
    chunk_overlap: int = 100

    # ── Retrieval ─────────────────────────────────────────────────────────────
    retrieval_k_initial: int = 20
    retrieval_k_final:   int = 5

    # ── Agent limits ──────────────────────────────────────────────────────────
    max_validation_retries: int = 2

    # ── Default quotas (per-user daily) ──────────────────────────────────────
    quota_max_queries_daily:  int = 200
    quota_max_uploads_daily:  int = 20
    quota_max_tokens_daily:   int = 500_000

    # ── Langfuse ──────────────────────────────────────────────────────────────
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host:       str = "https://cloud.langfuse.com"

    # ── Sentry ────────────────────────────────────────────────────────────────
    sentry_dsn:                str = ""
    sentry_traces_sample_rate: float = 0.1  # 10% of transactions

    # ── Telegram alerts ───────────────────────────────────────────────────────
    telegram_bot_token: str = ""
    telegram_chat_id:   str = ""  # your personal chat ID or group

    @property
    def use_azure(self) -> bool:
        return bool(self.azure_openai_endpoint and self.azure_openai_api_key)

    @property
    def sentry_enabled(self) -> bool:
        return bool(self.sentry_dsn and self.environment == "production")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
