from typing import Literal

from pydantic import BaseModel

Severity = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
SEVERITY_RANK: dict[str, int] = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}


class Alert(BaseModel):
    id: str
    ts: str  # UTC ISO-8601
    service: str
    detector: Literal["error_rate", "latency", "silence"]
    severity: Severity
    metric: str
    current: float
    baseline_median: float | None
    baseline_mad: float | None
    z: float | None
    window_seconds: int
    sample_lines: list[str]
    message: str
