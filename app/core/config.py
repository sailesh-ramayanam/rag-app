from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Database
    database_url: str = "postgresql+asyncpg://vault_user:vault_password@db:5432/vault_db"
    sync_database_url: str = "postgresql://vault_user:vault_password@db:5432/vault_db"
    
    # Redis
    redis_url: str = "redis://redis:6379/0"
    
    # Embeddings (sentence-transformers)
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dimensions: int = 384  # Dimension for all-MiniLM-L6-v2
    
    # Storage
    storage_path: str = "/app/storage"
    
    # Chunking settings
    chunk_size: int = 1000
    chunk_overlap: int = 200
    
    class Config:
        env_file = ".env"
        extra = "allow"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
