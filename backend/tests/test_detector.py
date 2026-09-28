import random

from app.config import Settings
from app.detector import Detector
from app.parser import LogEvent

BUCKET = 5
T0 = 1_800_000_000.0  # aligned to a bucket boundary


def feed(
    det: Detector, t: float, service: str, n: int, error_rate: float, latency: float = 80
) -> None:
    """Spread n events for `service` across the bucket starting at t."""
    for i in range(n):
        err = random.random() < error_rate
        det.ingest(
            LogEvent(
                t + i * BUCKET / n, "ERROR" if err else "INFO", service, latency, "m", f"line {i}"
            )
        )


def run(det: Detector, ticks: int, start: int, service: str, n: int, rate: float, **kw):
    alerts = []
    for k in range(start, start + ticks):
        t = T0 + k * BUCKET
        feed(det, t, service, n, rate, **kw)
        _, fired = det.evaluate(t + BUCKET - 0.01)
        alerts += fired
    return alerts


def settings() -> Settings:
    return Settings(_env_file=None)


def test_warmup_never_alerts() -> None:
    random.seed(1)
    det = Detector(settings())
    assert run(det, 11, 0, "payment-service", 50, 0.02) == []
    assert det.series["payment-service"].error_rate.warming_up


def test_spike_fires_with_severity_and_samples() -> None:
    random.seed(2)
    det = Detector(settings())
    assert run(det, 30, 0, "payment-service", 50, 0.02) == []
    alerts = run(det, 6, 30, "payment-service", 50, 0.40)
    er = [a for a in alerts if a.detector == "error_rate"]
    assert er, "error spike should fire"
    assert er[0].severity in {"LOW", "MEDIUM", "HIGH"}
    assert any(a.severity == "HIGH" for a in er), "severity escalates as the window fills"
    assert len(er) <= 3, "cooldown lets through escalations only"
    assert er[0].sample_lines and er[0].baseline_median is not None


def test_low_volume_noise_does_not_fire() -> None:
    random.seed(3)
    det = Detector(settings())
    run(det, 30, 0, "auth-service", 50, 0.02)
    run(det, 12, 30, "auth-service", 0, 0.0)  # let the window drain
    alerts = run(det, 3, 42, "auth-service", 1, 1.0)  # 3 errors in 3 lines = 100%, tiny volume
    assert [a for a in alerts if a.detector == "error_rate"] == []


def test_baseline_not_poisoned_by_incident() -> None:
    random.seed(4)
    det = Detector(settings())
    run(det, 30, 0, "payment-service", 50, 0.02)
    before = det.series["payment-service"].error_rate.stats()
    run(det, 24, 30, "payment-service", 50, 0.40)  # 2 minutes of incident
    after = det.series["payment-service"].error_rate.stats()
    assert before and after
    assert abs(after[0] - before[0]) < 0.01


def test_latency_spike_fires() -> None:
    random.seed(5)
    det = Detector(settings())
    run(det, 30, 0, "api-gateway", 50, 0.0, latency=80)
    alerts = run(det, 3, 30, "api-gateway", 50, 0.0, latency=2000)
    assert any(a.detector == "latency" for a in alerts)


def test_silence_fires_critical() -> None:
    random.seed(6)
    det = Detector(settings())
    run(det, 30, 0, "inventory-service", 50, 0.02)
    alerts = []
    for k in range(30, 34):  # 20 s with no inventory lines
        _, fired = det.evaluate(T0 + k * BUCKET + BUCKET - 0.01)
        alerts += fired
    silence = [a for a in alerts if a.detector == "silence"]
    assert len(silence) == 1 and silence[0].severity == "CRITICAL"


def test_alerts_stop_soon_after_recovery() -> None:
    random.seed(7)
    det = Detector(settings())
    run(det, 30, 0, "payment-service", 50, 0.02)
    assert run(det, 9, 30, "payment-service", 50, 0.40), "spike fires"
    run(det, 4, 39, "payment-service", 50, 0.02)  # 20 s of normal traffic
    # the 60 s window still holds the spike, but the latest 15 s are normal
    metrics, alerts = det.evaluate(T0 + 43 * BUCKET + BUCKET - 0.01)
    assert metrics["payment-service"]["error_rate"] > 0.1
    assert not metrics["payment-service"]["anomalous"]
    assert alerts == []
