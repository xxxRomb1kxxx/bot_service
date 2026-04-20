"""
config/__init__.py — конфигурация Telegram-бота.

Переменные окружения:
  BOT_TOKEN      — токен Telegram-бота (обязательно)
  BACKEND_URL    — URL FastAPI-сервиса агента (default: http://localhost:8000)
  ADMIN_IDS      — Telegram ID администраторов через запятую (например: 123456789,987654321)
  LOG_LEVEL      — уровень логирования (default: INFO)
"""
import logging
import sys
from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LOG_FORMAT = "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"


class Settings(BaseSettings):
    """Настройки Telegram-бота."""

    bot_token: str = Field(..., description="Telegram Bot Token")
    backend_url: str = Field(default="http://localhost:8000", description="URL агентского FastAPI-сервиса")

    # Список Telegram ID администраторов.
    # Пример в .env: ADMIN_IDS=123456789,987654321
    admin_ids: List[int] = Field(default_factory=list)

    log_level: str = Field(default="INFO")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in allowed:
            raise ValueError(f"log_level must be one of {allowed}")
        return upper

    @field_validator("admin_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, v: object) -> List[int]:
        """Принимает '123,456', одиночный int или уже список."""
        if isinstance(v, int):
            return [v]
        if isinstance(v, str):
            return [int(x.strip()) for x in v.split(",") if x.strip().isdigit()]
        return v or []


def setup_logging(level: str = "INFO") -> None:
    """Настраивает корневой логгер."""
    logging.basicConfig(
        level=logging.getLevelName(level),
        format=LOG_FORMAT,
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Синглтон через lru_cache."""
    return Settings()