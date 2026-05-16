from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # Azure OpenAI
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_api_version: str = "2024-08-01-preview"

    # Deployment names
    azure_deployment_gpt4o: str = "gpt-4o"
    azure_deployment_gpt4o_mini: str = "gpt-4o-2"
    azure_deployment_embedding: str = "text-embedding-3-large"

    # Direct OpenAI fallback
    openai_api_key: str = ""

    # Redis
    redis_url: str = "redis://localhost:6379"

    # ChromaDB
    chroma_persist_dir: str = "./chroma_db"

    # App
    log_level: str = "INFO"
    environment: str = "development"

    # Chunking defaults
    chunk_size: int = 500
    chunk_overlap: int = 100

    # Retrieval defaults
    retrieval_k_initial: int = 20
    retrieval_k_final: int = 5

    # Agent limits
    max_validation_retries: int = 2

    @property
    def use_azure(self) -> bool:
        return bool(self.azure_openai_endpoint and self.azure_openai_api_key)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
