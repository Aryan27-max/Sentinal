"""All tunables for Sentinel. Detectors read thresholds from here, never from literals.

Values come from environment variables or a `.env` file (repo root, then backend/),
matching ARCHITECTURE.md §14. Relative paths are resolved against backend/.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ingest
    log_path: Path = Path("../data/logs/app.log")
    tail_poll_ms: int = 200
    tail_from_start: bool = False

    # sliding window + baseline
    bucket_seconds: int = 5
    window_seconds: int = 60
    baseline_points: int = 60
    warmup_points: int = 12
    mad_floor: float = 0.005

    # detectors + severity
    z_low: float = 3.0
    z_medium: float = 5.0
    z_high: float = 8.0
    critical_error_rate: float = 0.5
    min_volume: int = 20
    min_abs_delta: float = 0.02
    silence_seconds: float = 15.0
    recent_buckets: int = 3  # an alert also needs the latest 15 s to be elevated
    cooldown_seconds: float = 30.0  # max one alert per (service, detector) unless severity rises
    latency_mad_floor_ms: float = 10.0  # MAD_FLOOR is in error-rate units; latency needs its own
    latency_min_abs_delta_ms: float = 100.0
    slow_line_ms: float = 1000.0  # lines slower than this are kept as latency sample lines
    history_points: int = 120  # chart points kept per series (10 min at 5 s)
    ping_seconds: float = 20.0

    # incidents
    resolve_ticks: int = 3
    correlation_seconds: float = 20.0

    # generator
    generator_enabled: bool = True
    generator_rate: float = 40.0
    log_max_bytes: int = 50_000_000  # generator truncates the file past this; the tailer copes

    # built dashboard served by FastAPI in production
    static_dir: Path = Path("../frontend/dist")

    # sinks
    dry_run: bool = True
    aws_region: str = "ap-south-1"
    sns_topic_arn: str = ""
    cw_log_group: str = "/sentinel/alerts"
    cw_log_stream: str = "demo"

    # narrator
    anthropic_api_key: SecretStr = SecretStr("")

    @property
    def resolved_log_path(self) -> Path:
        return _resolve(self.log_path)

    @property
    def resolved_static_dir(self) -> Path:
        return _resolve(self.static_dir)


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else (BACKEND_DIR / path).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()
