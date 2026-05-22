from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # ── Auth ──────────────────────────────────────────────────────────────────
    secret_key: str = Field(default="change-me-in-production-32-chars-min", min_length=16)
    allowed_origins: list[str] = Field(default=["http://localhost:5173", "http://localhost:3000"])

    # ── Database ──────────────────────────────────────────────────────────────
    # SQLite for local dev; set DATABASE_URL=postgresql+asyncpg://... in production
    database_url: str = "sqlite+aiosqlite:///./rag_studio.db"

    # ── Azure OpenAI ──────────────────────────────────────────────────────────
    azure_openai_endpoint:    str = ""
    azure_openai_api_key:     str = ""
    azure_openai_api_version: str = "2024-08-01-preview"

    # Deployment names — must match the deployment names in the Azure portal
    azure_openai_deployment_gpt4o:       str = "gpt-4o"
    azure_openai_deployment_gpt4o_mini:  str = "gpt-4o-mini"
    azure_openai_deployment_embedding:   str = "text-embedding-3-large"

    # ── Direct OpenAI fallback ────────────────────────────────────────────────
    openai_api_key: str = ""

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379"

    # ── ChromaDB ──────────────────────────────────────────────────────────────
    chroma_persist_dir: str = "./chroma_db"

    # ── App ───────────────────────────────────────────────────────────────────
    log_level:   str = "INFO"
    environment: str = "development"

    # ── Chunking defaults ─────────────────────────────────────────────────────
    chunk_size:    int = 500
    chunk_overlap: int = 100

    # ── Retrieval defaults ────────────────────────────────────────────────────
    retrieval_k_initial: int = 20
    retrieval_k_final:   int = 5

    # ── Agent limits ──────────────────────────────────────────────────────────
    max_validation_retries: int = 2

    # ── Rate limits ───────────────────────────────────────────────────────────
    rate_limit_queries_per_hour: int = 100
    rate_limit_uploads_per_day:  int = 20

    # ── Langfuse ──────────────────────────────────────────────────────────────
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host:       str = "https://cloud.langfuse.com"

    @property
    def use_azure(self) -> bool:
        return bool(self.azure_openai_endpoint and self.azure_openai_api_key)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
