from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # .env и относительный путь к SQLite считаются от папки backend/, а не от текущей директории
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    keitaro_url: str = "https://tlgk.host/admin_api/v1"
    keitaro_api_key: str = ""
    keitaro_timeout: float = 30.0
    keitaro_cache_ttl: float = 60.0  # сек, кэш справочников (кампании, офферы, домены...)

    database_url: str = "sqlite+aiosqlite:///./app.db"

    geo_redirect_url: str = "https://google.com"
    cors_origins: str = "http://localhost:5173"

    @field_validator("database_url")
    @classmethod
    def resolve_sqlite_path(cls, v: str) -> str:
        prefix = "sqlite+aiosqlite:///"
        if v.startswith(prefix):
            path = v[len(prefix):]
            if path and path != ":memory:" and not Path(path).is_absolute():
                return prefix + (BACKEND_DIR / path).resolve().as_posix()
        return v

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
