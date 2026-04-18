"""Application settings loaded from environment variables via pydantic-settings."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


_PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- General ---
    app_name: str = "Civil Agent"
    debug: bool = False
    log_level: str = "INFO"

    # --- API ---
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: list[str] = ["*"]

    # --- Storage ---
    upload_dir: Path = _PROJECT_ROOT / "data" / "uploads"
    output_dir: Path = _PROJECT_ROOT / "data" / "outputs"

    # --- Database (future) ---
    database_url: Optional[str] = None

    # --- Redis / Celery ---
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://redis:6379/0"
    celery_result_backend: str = "redis://redis:6379/1"

    # --- Flower monitoring ---
    flower_user: str = "admin"
    flower_password: str = "changeme"

    # --- CV Model paths ---
    wall_segmenter_weights: Optional[Path] = None
    symbol_detector_weights: Optional[Path] = None

    # --- LLM ---
    anthropic_api_key: Optional[str] = None

    # --- AWS S3 (future) ---
    s3_bucket: Optional[str] = None
    aws_region: str = "us-east-1"

    # --- Thresholds & constants ---
    default_wall_thickness_mm: float = 200.0
    snap_tolerance_mm: float = 50.0
    angle_snap_degrees: float = 3.0
    min_room_area_m2: float = 1.0


settings = Settings()
