from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Database
    database_url: str
    sync_database_url: str
    
    # Redis
    redis_url: str
    
    # Embeddings (sentence-transformers)
    embedding_model: str
    embedding_dimensions: int
    
    # Storage
    storage_path: str
    
    # Chunking settings (optional with defaults)
    chunk_size: int = 1000
    chunk_overlap: int = 200
    
    # LLM settings
    llm_provider: str
    llm_model: str
    openai_api_key: str
    
    class Config:
        env_file = ".env"
        extra = "allow"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
