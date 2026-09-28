"""Parse `<iso-ts> key=value key="quoted value" ...` lines (ARCHITECTURE.md §4)."""

import re
from dataclasses import dataclass
from datetime import datetime

KV_RE = re.compile(r'(\w+)=("(?:[^"\\]|\\.)*"|\S+)')
ERROR_LEVELS = frozenset({"ERROR", "FATAL"})


@dataclass(slots=True)
class LogEvent:
    ts: float  # epoch seconds
    level: str
    service: str
    latency_ms: float | None
    msg: str
    raw: str

    @property
    def is_error(self) -> bool:
        return self.level in ERROR_LEVELS


def parse_line(line: str) -> LogEvent | None:
    """Return a LogEvent, or None for anything unparseable. Never raises."""
    line = line.strip()
    ts_text, _, rest = line.partition(" ")
    if not rest:
        return None
    try:
        ts = datetime.fromisoformat(ts_text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None

    fields = {k: v[1:-1] if v.startswith('"') else v for k, v in KV_RE.findall(rest)}
    level = fields.get("level", "").upper()
    service = fields.get("service")
    if not level or not service:
        return None

    latency: float | None
    try:
        latency = float(fields["latency_ms"])
    except (KeyError, ValueError):
        latency = None

    return LogEvent(ts, level, service, latency, fields.get("msg", ""), line)
