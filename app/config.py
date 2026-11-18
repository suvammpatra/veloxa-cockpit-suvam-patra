"""Application settings.

Every setting has a working default, so the app runs from a fresh clone with
no .env file and no API key. Values can be overridden with VELOXA_* environment
variables or a .env file in the project root.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VELOXA_",
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_dir: Path = Path("data")
    db_filename: str = "cockpit.db"
    payroll_db_filename: str = "payroll.db"
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"
    llm_enabled: bool = False

    @property
    def data_path(self) -> Path:
        """Data directory, resolved against the project root when relative."""
        path = self.data_dir
        return path if path.is_absolute() else PROJECT_ROOT / path

    @property
    def database_path(self) -> Path:
        return self.data_path / self.db_filename

    @property
    def payroll_path(self) -> Path:
        """The restricted payroll store, a separate file (DECISIONS.md 3)."""
        return self.data_path / self.payroll_db_filename

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.database_path.as_posix()}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
