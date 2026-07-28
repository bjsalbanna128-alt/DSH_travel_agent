"""Application configuration via pydantic-settings, loaded from .env."""

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_env() -> str:
    """Locate .env file by searching upward from this file and CWD."""
    candidates = [
        Path(__file__).resolve().parent.parent.parent / ".env",
        Path.cwd() / ".env",
        Path.cwd().parent / ".env",
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return str(Path(__file__).resolve().parent.parent.parent / ".env")


_ENV_PATH = _find_env()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_PATH,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── App ──────────────────────────────────────────────
    app_env: str = "development"
    debug: bool = True
    log_level: str = "INFO"

    # ── DeepSeek ──────────────────────────────────────────
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"

    # ── Amap ─────────────────────────────────────────────
    amap_api_key: str = ""

    # ── QWeather ─────────────────────────────────────────
    qweather_api_key: str = ""

    # ── Database ───────────────────────────────────────────
    # Default to SQLite — set to PostgreSQL URL via .env for production
    database_url: str = ""

    # ── Redis ─────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379"

    # ── ChromaDB ──────────────────────────────────────────
    chroma_persist_path: str = "./chroma_data"
    embedding_model_name: str = "BAAI/bge-small-zh-v1.5"

    # ── JWT ───────────────────────────────────────────────
    jwt_secret_key: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440


settings = Settings()
