"""Wires generator → file → tailer → parser → detector → (WebSocket, sinks, in-memory store)."""

import asyncio
import logging
import time
from collections import defaultdict, deque
from typing import Any

from app.api.ws import Hub
from app.config import Settings
from app.detector import ALL, Detector, iso
from app.generator import SERVICES, Generator
from app.models import Alert
from app.parser import parse_line
from app.sinks import Dispatcher
from app.tailer import Tailer

log = logging.getLogger("sentinel.pipeline")

RECENT_ALERTS = 200


class Sentinel:
    def __init__(self, settings: Settings) -> None:
        self.s = settings
        path = settings.resolved_log_path
        self.generator = Generator(path, settings.generator_rate)
        self.tailer = Tailer(path, settings.tail_poll_ms, settings.tail_from_start)
        self.detector = Detector(settings)
        self.hub = Hub()
        self.dispatcher = Dispatcher(settings)
        self.alerts: deque[Alert] = deque(maxlen=RECENT_ALERTS)
        self.history: dict[str, deque[dict[str, Any]]] = defaultdict(
            lambda: deque(maxlen=settings.history_points)
        )
        self.latest: dict[str, Any] = {}
        self.lines_total = 0
        self.unparsed = 0
        self.lines_per_sec = 0.0
        self._lines_since_tick = 0
        self._tasks: list[asyncio.Task[None]] = []

    # --- lifecycle ---
    async def start(self) -> None:
        self.s.resolved_log_path.parent.mkdir(parents=True, exist_ok=True)
        await self.dispatcher.setup()
        runners = [self._ingest(), self._tick(), self._ping(), self.dispatcher.run()]
        if self.s.generator_enabled:
            runners.append(self.generator.run())
        self._tasks = [asyncio.create_task(r) for r in runners]

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    # --- loops ---
    async def _ingest(self) -> None:
        async for lines in self.tailer.follow():
            for line in lines:
                event = parse_line(line)
                if event is None:
                    self.unparsed += 1
                    continue
                self.detector.ingest(event)
                self.lines_total += 1
                self._lines_since_tick += 1

    async def _tick(self) -> None:
        while True:
            await asyncio.sleep(self.s.bucket_seconds)
            try:
                await self._evaluate()
            except Exception:
                log.exception("Tick failed; continuing")

    async def _evaluate(self) -> None:
        now = time.time()
        metrics, alerts = self.detector.evaluate(now)
        self.lines_per_sec = round(self._lines_since_tick / self.s.bucket_seconds, 1)
        self._lines_since_tick = 0

        for name, m in metrics.items():
            band = m["band"] or [None, None]
            self.history[name].append(
                {
                    "ts": iso(now),
                    "error_rate": m["error_rate"],
                    "p95": m["p95"],
                    "baseline_median": m["baseline_median"],
                    "band_lo": band[0],
                    "band_hi": band[1],
                    "anomalous": m["anomalous"],
                }
            )
        self.latest = self._metrics_payload(now, metrics)
        await self.hub.broadcast("metrics", self.latest)

        for alert in alerts:
            self.alerts.appendleft(alert)
            await self.hub.broadcast("alert", alert.model_dump(mode="json"))
            self.dispatcher.submit(alert)

    async def _ping(self) -> None:
        while True:
            await asyncio.sleep(self.s.ping_seconds)
            await self.hub.broadcast("ping", {"ts": iso(time.time())})

    # --- views ---
    def _metrics_payload(self, now: float, metrics: dict[str, Any]) -> dict[str, Any]:
        return {
            "ts": iso(now),
            "services": metrics,
            "lines_per_sec": self.lines_per_sec,
            "warming_up": self.detector.warming_up,
            "chaos": self.generator.active(),
        }

    def chaos(self, name: str) -> dict[str, Any]:
        duration = self.generator.trigger(name)
        return {"scenario": name, "active": name != "recover", "duration": duration}

    def snapshot(self) -> dict[str, Any]:
        return {
            "services": [ALL, *SERVICES],
            "metrics": self.latest or None,
            "history": {name: list(points) for name, points in self.history.items()},
            "alerts": [a.model_dump(mode="json") for a in list(self.alerts)[:50]],
            "chaos": self.generator.active(),
            "warming_up": self.detector.warming_up,
            "config": {
                "bucket_seconds": self.s.bucket_seconds,
                "window_seconds": self.s.window_seconds,
                "warmup_points": self.s.warmup_points,
                "z_low": self.s.z_low,
                "z_medium": self.s.z_medium,
                "z_high": self.s.z_high,
            },
        }

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "warming_up": self.detector.warming_up,
            "lines_per_sec": self.lines_per_sec,
            "lines_total": self.lines_total,
            "unparsed": self.unparsed,
            "clients": len(self.hub.clients),
            "sinks": self.dispatcher.status,
        }
