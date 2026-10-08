"""Application configuration."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment with sensible defaults."""

    model_config = SettingsConfigDict(
        env_prefix="GEO_API_",
        env_file=".env",
        extra="ignore",
    )

    app_name: str = "Geospatial File Measurement API"
    debug: bool = False
    max_upload_bytes: int = 50 * 1024 * 1024  # 50 MB
    uploads_dir: Path = Path("uploads")
    allowed_extensions: frozenset[str] = frozenset({".kml", ".zip"})

    def ensure_uploads_dir(self) -> Path:
        """Create uploads directory if missing and return its path."""
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        return self.uploads_dir


settings = Settings()
