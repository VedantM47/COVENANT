"""Application settings — reads from env + .env file."""
from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    covenant_root: Path = Path("D:/covenant")
    hf_home: Path = Path("D:/covenant/models/hf")
    torch_home: Path = Path("D:/covenant/models/torch")

    app_secret_key: str = "dev-secret-key-change-in-prod"
    llm_provider: str = "mock"

    google_api_key: str = ""
    anthropic_api_key: str = ""
    openrouter_api_key: str = ""
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "us-east-1"
    sec_edgar_user_agent: str = "CovenantPlatform audit@covenant.local"
    ffiec_cdr_username: str = ""
    ffiec_cdr_bearer_token: str = ""

    @property
    def engagements_dir(self) -> Path:
        return self.covenant_root / "engagements"

    @property
    def models_dir(self) -> Path:
        return self.covenant_root / "models"

    @property
    def cache_dir(self) -> Path:
        return self.covenant_root / "cache"

    @property
    def logs_dir(self) -> Path:
        return self.covenant_root / "logs"

    @property
    def tmp_dir(self) -> Path:
        return self.covenant_root / "tmp"

    def engagement_dir(self, engagement_id: str) -> Path:
        return self.engagements_dir / engagement_id

    def ensure_engagement_dirs(self, engagement_id: str) -> Path:
        """Create all subdirectories for a new engagement."""
        base = self.engagement_dir(engagement_id)
        for sub in ["raw", "parsed", "chunks", "faiss/archive", "state", "audit", "exports/exception_memos"]:
            (base / sub).mkdir(parents=True, exist_ok=True)
        return base


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
        # Ensure top-level dirs exist
        for d in [
            _settings.engagements_dir,
            _settings.models_dir,
            _settings.cache_dir,
            _settings.logs_dir,
            _settings.tmp_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)
    return _settings
