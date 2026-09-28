"""Sliding-window metrics, robust baselines, and the error-rate / latency / silence detectors.

Per series (each service, plus "all" for the dashboard), events land in 5 s buckets keyed on
event time. Every tick we sum the last 60 s of buckets, compare the window's error rate and
p95 latency to a rolling median + MAD baseline, and raise explainable alerts.
"""

import math
import statistics
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.config import Settings
from app.models import SEVERITY_RANK, Alert
from app.parser import LogEvent

ALL = "all"  # aggregate series: shown on the dashboard, never alerts
MAD_TO_SIGMA = 0.6745


@dataclass
class Bucket:
    total: int = 0
    errors: int = 0
    latencies: list[float] = field(default_factory=list)


class Baseline:
    """Rolling median + MAD over recent normal values. Anomalous values are never added."""

    def __init__(self, maxlen: int, warmup: int, mad_floor: float) -> None:
        self.values: deque[float] = deque(maxlen=maxlen)
        self.warmup = warmup
        self.mad_floor = mad_floor

    @property
    def warming_up(self) -> bool:
        return len(self.values) < self.warmup

    def add(self, value: float) -> None:
        self.values.append(value)

    def stats(self) -> tuple[float, float] | None:
        """(median, MAD clamped to the floor), or None with no history."""
        if not self.values:
            return None
        median = statistics.median(self.values)
        mad = statistics.median(abs(v - median) for v in self.values)
        return median, max(mad, self.mad_floor)

    def z(self, x: float) -> float:
        stats = self.stats()
        if stats is None:
            return 0.0
        median, mad = stats
        return MAD_TO_SIGMA * (x - median) / mad

    def band(self, z_threshold: float) -> list[float] | None:
        """Values inside this band score below z_threshold."""
        stats = self.stats()
        if stats is None:
            return None
        median, mad = stats
        half = z_threshold * mad / MAD_TO_SIGMA
        return [max(0.0, median - half), median + half]


@dataclass
class Series:
    error_rate: Baseline
    p95: Baseline
    buckets: dict[int, Bucket] = field(default_factory=dict)
    last_seen: float | None = None
    recent: deque[str] = field(default_factory=lambda: deque(maxlen=3))
    error_lines: deque[str] = field(default_factory=lambda: deque(maxlen=3))
    slow_lines: deque[str] = field(default_factory=lambda: deque(maxlen=3))
    last_alert: dict[str, tuple[float, str]] = field(default_factory=dict)  # detector -> (ts, sev)


def p95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class Detector:
    def __init__(self, settings: Settings) -> None:
        self.s = settings
        self.series: dict[str, Series] = {}
        self.n_buckets = settings.window_seconds // settings.bucket_seconds

    def _get(self, key: str) -> Series:
        if key not in self.series:
            s = self.s
            self.series[key] = Series(
                error_rate=Baseline(s.baseline_points, s.warmup_points, s.mad_floor),
                p95=Baseline(s.baseline_points, s.warmup_points, s.latency_mad_floor_ms),
            )
        return self.series[key]

    @property
    def warming_up(self) -> bool:
        return ALL not in self.series or self.series[ALL].error_rate.warming_up

    # --- ingest ---
    def ingest(self, ev: LogEvent) -> None:
        key = int(ev.ts // self.s.bucket_seconds)
        for name in (ev.service, ALL):
            series = self._get(name)
            bucket = series.buckets.setdefault(key, Bucket())
            bucket.total += 1
            if ev.is_error:
                bucket.errors += 1
                series.error_lines.append(ev.raw)
            if ev.latency_ms is not None:
                bucket.latencies.append(ev.latency_ms)
                if ev.latency_ms >= self.s.slow_line_ms:
                    series.slow_lines.append(ev.raw)
            series.recent.append(ev.raw)
            series.last_seen = ev.ts if series.last_seen is None else max(series.last_seen, ev.ts)

    # --- evaluate ---
    def evaluate(self, now: float | None = None) -> tuple[dict[str, dict[str, Any]], list[Alert]]:
        """Run one tick. Returns per-series metrics and any alerts raised."""
        now = time.time() if now is None else now
        first_key = int(now // self.s.bucket_seconds) - self.n_buckets + 1
        metrics: dict[str, dict[str, Any]] = {}
        alerts: list[Alert] = []

        for name, series in self.series.items():
            for key in [k for k in series.buckets if k < first_key]:
                del series.buckets[key]
            buckets = series.buckets.values()
            total = sum(b.total for b in buckets)
            errors = sum(b.errors for b in buckets)
            latencies = [x for b in buckets for x in b.latencies]
            can_alert = name != ALL

            m: dict[str, Any] = {"volume": total, "silent": False, "anomalous": False}

            er_value = errors / total if total else None
            er = self._check(
                series.error_rate,
                er_value,
                total,
                self.s.min_abs_delta,
                now=now,
                name=name,
                series=series,
                detector="error_rate",
                can_alert=can_alert,
                alerts=alerts,
            )
            m.update(
                error_rate=er_value,
                baseline_median=er["median"],
                band=series.error_rate.band(self.s.z_low),
                z=er["z"],
                anomalous=er["anomalous"],
            )

            p95_value = p95(latencies) if latencies else None
            lat = self._check(
                series.p95,
                p95_value,
                len(latencies),
                self.s.latency_min_abs_delta_ms,
                now=now,
                name=name,
                series=series,
                detector="latency",
                can_alert=can_alert,
                alerts=alerts,
            )
            m.update(
                p95=p95_value,
                p95_baseline_median=lat["median"],
                p95_band=series.p95.band(self.s.z_low),
                p95_anomalous=lat["anomalous"],
                warming_up=series.error_rate.warming_up,
            )

            if can_alert and self._is_silent(series, now):
                m["silent"] = True
                gap = now - (series.last_seen or now)
                alert = self._alert(
                    series,
                    name,
                    "silence",
                    "CRITICAL",
                    now,
                    metric="seconds_since_last_line",
                    current=round(gap, 1),
                    median=None,
                    mad=None,
                    z=None,
                    samples=list(series.recent),
                    message=f"{name} has written no logs for {gap:.0f}s",
                )
                if alert:
                    alerts.append(alert)

            metrics[name] = m
        return metrics, alerts

    def _is_silent(self, series: Series, now: float) -> bool:
        # Only a service with an established baseline (it normally logs) can go silent.
        return (
            series.last_seen is not None
            and not series.error_rate.warming_up
            and now - series.last_seen >= self.s.silence_seconds
        )

    def _check(
        self,
        baseline: Baseline,
        value: float | None,
        volume: int,
        min_abs_delta: float,
        *,
        now: float,
        name: str,
        series: Series,
        detector: str,
        can_alert: bool,
        alerts: list[Alert],
    ) -> dict[str, Any]:
        """Score one metric against its baseline, maybe alert, and learn from normal values."""
        stats = baseline.stats()
        median = stats[0] if stats else None
        if value is None:
            return {"median": median, "z": None, "anomalous": False}

        z = baseline.z(value)
        anomalous = (
            not baseline.warming_up
            and volume >= self.s.min_volume
            and z >= self.s.z_low
            and median is not None
            and value - median >= min_abs_delta
        )
        if not anomalous and volume >= self.s.min_volume:
            baseline.add(value)

        if anomalous and can_alert and stats:
            alert = self._metric_alert(series, name, detector, value, stats, z, now)
            if alert:
                alerts.append(alert)
        return {"median": median, "z": round(z, 2), "anomalous": anomalous}

    def _metric_alert(
        self,
        series: Series,
        name: str,
        detector: str,
        value: float,
        stats: tuple[float, float],
        z: float,
        now: float,
    ) -> Alert | None:
        median, mad = stats
        s = self.s
        severity = "HIGH" if z >= s.z_high else "MEDIUM" if z >= s.z_medium else "LOW"
        if detector == "error_rate":
            if value >= s.critical_error_rate:
                severity = "CRITICAL"
            samples = list(series.error_lines)
            message = f"{name} error rate {value:.1%} vs baseline {median:.1%} (z={z:.1f})"
            metric = "error_rate"
        else:
            samples = list(series.slow_lines) or list(series.recent)
            message = f"{name} p95 latency {value:.0f}ms vs baseline {median:.0f}ms (z={z:.1f})"
            metric = "p95_latency_ms"
        return self._alert(
            series,
            name,
            detector,
            severity,
            now,
            metric=metric,
            current=value,
            median=median,
            mad=mad,
            z=z,
            samples=samples,
            message=message,
        )

    def _alert(
        self,
        series: Series,
        name: str,
        detector: str,
        severity: str,
        now: float,
        *,
        metric: str,
        current: float,
        median: float | None,
        mad: float | None,
        z: float | None,
        samples: list[str],
        message: str,
    ) -> Alert | None:
        """Build an alert unless the (service, detector) cooldown suppresses it.

        Within the cooldown only a severity escalation gets through, so an incident shows
        LOW → MEDIUM → HIGH once rather than a new alert every tick.
        """
        last = series.last_alert.get(detector)
        if (
            last
            and now - last[0] < self.s.cooldown_seconds
            and SEVERITY_RANK[severity] <= SEVERITY_RANK[last[1]]
        ):
            return None
        series.last_alert[detector] = (now, severity)
        return Alert(
            id=uuid.uuid4().hex[:12],
            ts=iso(now),
            service=name,
            detector=detector,  # type: ignore[arg-type]
            severity=severity,  # type: ignore[arg-type]
            metric=metric,
            current=round(current, 4),
            baseline_median=None if median is None else round(median, 4),
            baseline_mad=None if mad is None else round(mad, 4),
            z=None if z is None else round(z, 2),
            window_seconds=self.s.window_seconds,
            sample_lines=samples[-3:],
            message=message,
        )
