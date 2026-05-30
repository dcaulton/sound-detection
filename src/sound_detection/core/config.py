"""Core settings for sound-detection service."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Environment
    environment: str = "development"
    debug: bool = True

    # Service
    service_name: str = "sound-detection"
    host: str = "0.0.0.0"
    port: int = 8000

    # Database (Postgres on chakakhan, SQLite for local dev)
    database_url: str = "sqlite+aiosqlite:///./sound_detection.db"

    # MLflow tracking
    mlflow_tracking_uri: str = "http://localhost:5000"

    # Bioacoustics defaults
    default_confidence_threshold: float = 0.6
    audio_sample_rate: int = 48000


# Singleton instance
settings = Settings()
