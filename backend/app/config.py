from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://clipuser:clippass@localhost:5432/clipdb"
    REDIS_URL: str = "redis://localhost:6379/0"
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "ai-clip"
    MINIO_SECURE: bool = False
    JWT_SECRET: str = "change-me-in-production"
    JWT_EXPIRE_HOURS: int = 24
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_MODEL: str = "gpt-4o"
    WHISPER_MODEL: str = "whisper-1"

    class Config:
        env_file = ".env"


settings = Settings()
