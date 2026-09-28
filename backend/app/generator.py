"""Synthetic multi-service traffic written to the log file (ARCHITECTURE.md §4, §11).

The generator only writes the file; the detector only reads it (CLAUDE.md rule 6).
The file is opened per batch in append mode, so no handle is held between writes.
"""

import asyncio
import math
import random
import time
from datetime import UTC, datetime
from pathlib import Path

SERVICES = ("api-gateway", "auth-service", "payment-service", "inventory-service")

INFO_MSGS = {
    "api-gateway": [
        "GET /api/v1/orders 200",
        "GET /api/v1/products 200",
        "POST /api/v1/cart 201",
        "GET /healthz 200",
    ],
    "auth-service": [
        "token issued user_id={n}",
        "session refreshed user_id={n}",
        "login ok user_id={n}",
    ],
    "payment-service": [
        "charge authorized amount={n} currency=USD",
        "refund processed amount={n}",
        "payment intent created id=pi_{n}",
    ],
    "inventory-service": [
        "stock reserved sku=SKU-{n}",
        "stock level check sku=SKU-{n}",
        "restock event sku=SKU-{n}",
    ],
}
ERROR_MSGS = {
    "api-gateway": [
        "upstream timeout route=/api/v1/orders",
        "502 bad gateway upstream=auth-service",
    ],
    "auth-service": ["invalid token signature", "rate limit exceeded client={n}"],
    "payment-service": ["card declined by processor", "idempotency key conflict id=pi_{n}"],
    "inventory-service": ["stock reservation failed sku=SKU-{n}", "cache miss storm key=inv:{n}"],
}
DB_TIMEOUT_MSG = "DB connection timeout after 5000ms host=db-2"

SCENARIOS: dict[str, float] = {"db_outage": 45, "latency_spike": 45, "silence": 30}

BASE_ERROR_RATE = 0.02
LATENCY_MEDIAN_MS = 80  # lognormal sigma 0.49 puts p95 near 180 ms
LATENCY_SIGMA = 0.49


class Generator:
    def __init__(self, path: Path, rate: float) -> None:
        self.path = path
        self.rate = rate
        self.scenario_ends: dict[str, float] = {}  # name -> monotonic end time

    # --- scenarios ---
    def trigger(self, name: str) -> float:
        """Start a scenario (or `recover`). Returns its duration in seconds."""
        if name == "recover":
            self.scenario_ends.clear()
            return 0
        duration = SCENARIOS[name]
        self.scenario_ends[name] = time.monotonic() + duration
        return duration

    def active(self) -> dict[str, float]:
        """Active scenarios with seconds remaining."""
        now = time.monotonic()
        for name in [n for n, end in self.scenario_ends.items() if end <= now]:
            del self.scenario_ends[name]
        return {n: round(end - now, 1) for n, end in self.scenario_ends.items()}

    # --- traffic ---
    def make_line(self, active: dict[str, float]) -> str | None:
        service = random.choice(SERVICES)
        if service == "inventory-service" and "silence" in active:
            return None

        n = random.randint(1000, 9999)
        latency = random.lognormvariate(math.log(LATENCY_MEDIAN_MS), LATENCY_SIGMA)
        if service == "api-gateway" and "latency_spike" in active:
            latency = random.lognormvariate(math.log(1300), 0.25)  # p95 ~2 s

        if service == "payment-service" and "db_outage" in active and random.random() < 0.35:
            level, msg, latency = "ERROR", DB_TIMEOUT_MSG, random.uniform(5000, 5050)
        elif random.random() < BASE_ERROR_RATE:
            level, msg = "ERROR", random.choice(ERROR_MSGS[service]).format(n=n)
        else:
            roll = random.random()
            level = "DEBUG" if roll < 0.05 else "WARN" if roll < 0.08 else "INFO"
            msg = random.choice(INFO_MSGS[service]).format(n=n)

        ts = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        return f'{ts} level={level} service={service} latency_ms={latency:.0f} msg="{msg}"'

    def _append(self, lines: list[str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8", newline="\n") as f:
            f.write("".join(line + "\n" for line in lines))

    async def run(self) -> None:
        tick, carry = 0.1, 0.0
        while True:
            carry += self.rate * tick * random.uniform(0.8, 1.2)
            count, carry = int(carry), carry - int(carry)
            active = self.active()
            lines = [line for _ in range(count) if (line := self.make_line(active))]
            if lines:
                await asyncio.to_thread(self._append, lines)
            await asyncio.sleep(tick)
