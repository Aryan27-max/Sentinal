# Sentinel — Architecture

Real-time log anomaly detector with a live alert feed, explainable alerts, incident grouping, a chaos panel for live demos, and AWS SNS / CloudWatch alerting.

---

## 1. Goals

| Requirement (problem statement) | How Sentinel meets it |
|---|---|
| Monitor a continuously growing log file | `ingest/tailer.py` — async offset-based tail, survives truncation and rotation |
| Rolling error rate over a sliding window | `detect/window.py` — time-bucketed sliding window (5s buckets × 60s) |
| Baseline for normal behavior | `detect/baseline.py` — rolling median + MAD, anomaly-excluded, with warm-up |
| Detect deviations | `detect/detectors.py` — robust z-score on error rate + p95 latency, silence detection, new-signature detection |
| Severity levels | `detect/severity.py` — LOW / MEDIUM / HIGH / CRITICAL |
| Real-time frontend | FastAPI WebSocket `/ws` → React dashboard |
| Display alerts as generated | Live alert feed + incident cards |
| Push to CloudWatch Logs or SNS | `sinks/` — SNS + CloudWatch sinks, non-blocking, DRY_RUN fallback |

**Differentiators (the "wow"):** chaos panel the judge can press, explainable alerts, plain-English incident summary, never-seen-before error detection (Drain3), silence detection, incidents with auto-resolve, replay on a labeled public dataset with precision/recall.

---

## 2. High-level flow

```
                ┌──────────────────────┐
  Chaos Panel ─▶│ generator (asyncio)  │── writes ──▶ data/logs/app.log
  (POST /api/   └──────────────────────┘                   │
   chaos/...)                                               ▼
                                                  ┌──────────────────┐
                                                  │ tailer (offset,  │
                                                  │ rotation-safe)   │
                                                  └────────┬─────────┘
                                                           ▼
                                                  ┌──────────────────┐
                                                  │ parser → LogEvent│
                                                  └────────┬─────────┘
                                   ┌───────────────────────┼─────────────────────┐
                                   ▼                       ▼                     ▼
                           ┌──────────────┐      ┌──────────────────┐   ┌────────────────┐
                           │ sliding      │      │ signature miner  │   │ silence watch  │
                           │ window       │      │ (Drain3)         │   │ (last-seen ts) │
                           └──────┬───────┘      └────────┬─────────┘   └───────┬────────┘
                                  ▼                       │                     │
                           ┌──────────────┐               │                     │
                           │ baseline +   │               │                     │
                           │ robust z     │               │                     │
                           └──────┬───────┘               │                     │
                                  └───────────┬───────────┴─────────────────────┘
                                              ▼
                                     ┌──────────────────┐
                                     │ severity + Alert │
                                     └────────┬─────────┘
                                              ▼
                                     ┌──────────────────┐     ┌───────────────────┐
                                     │ incident manager │────▶│ LLM summary (opt) │
                                     │ (group, dedup,   │     │ template fallback │
                                     │  resolve)        │     └───────────────────┘
                                     └────────┬─────────┘
                           ┌──────────────────┼──────────────────┐
                           ▼                  ▼                  ▼
                   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
                   │ WS broadcast │   │ sink queue → │   │ in-memory    │
                   │ /ws          │   │ SNS / CW /   │   │ store (REST) │
                   └──────┬───────┘   │ console      │   └──────────────┘
                          ▼           └──────────────┘
                   React dashboard
```

The generator writes to a real file and the tailer reads it. The file boundary is kept honest on purpose: the detector never gets events directly from the generator.

---

## 3. Directory layout

```
sentinel/
├── CLAUDE.md
├── ARCHITECTURE.md
├── README.md
├── .env.example
├── data/logs/                    # app.log lives here (gitignored)
├── backend/
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py               # FastAPI app, lifespan starts pipeline tasks
│   │   ├── config.py             # pydantic-settings, all tunables
│   │   ├── models.py             # LogEvent, WindowStats, Alert, Incident, WS messages
│   │   ├── pipeline.py           # wires tailer → parser → detectors → incidents → outputs
│   │   ├── ingest/
│   │   │   ├── tailer.py
│   │   │   └── parser.py
│   │   ├── detect/
│   │   │   ├── window.py
│   │   │   ├── baseline.py
│   │   │   ├── signatures.py     # Drain3 wrapper
│   │   │   ├── detectors.py      # error-rate, latency, silence, new-signature
│   │   │   └── severity.py
│   │   ├── incidents/
│   │   │   └── manager.py
│   │   ├── sinks/
│   │   │   ├── base.py           # AlertSink protocol
│   │   │   ├── console.py
│   │   │   ├── sns.py
│   │   │   ├── cloudwatch.py
│   │   │   └── dispatcher.py     # async queue, retry with backoff, never blocks pipeline
│   │   ├── summary/
│   │   │   └── narrator.py       # LLM summary with template fallback
│   │   ├── generator/
│   │   │   ├── generator.py      # realistic multi-service traffic
│   │   │   └── scenarios.py      # db_outage, latency_spike, unknown_crash, silence, recover
│   │   └── api/
│   │       ├── routes.py
│   │       └── ws.py             # connection manager + broadcast
│   └── tests/
├── frontend/                     # React + Vite + TS + Tailwind + Framer Motion + Recharts
│   └── src/
│       ├── main.tsx, App.tsx
│       ├── lib/ws.ts             # reconnecting WebSocket client
│       ├── lib/api.ts
│       ├── store/useSentinel.ts  # zustand store
│       ├── components/
│       │   ├── NavBar.tsx        # glass bar + system status pill
│       │   ├── MetricCard.tsx
│       │   ├── LiveChart.tsx     # error rate + shaded baseline band + anomaly markers
│       │   ├── AlertFeed.tsx
│       │   ├── IncidentCard.tsx
│       │   ├── IncidentSheet.tsx # detail sheet: why, samples, summary, timeline
│       │   └── ChaosPanel.tsx
│       └── styles/index.css
└── scripts/
    └── replay_loghub.py          # replays Loghub HDFS, reports precision/recall
```

---

## 4. Log format

The generator emits key=value lines:

```
2026-09-28T15:21:04.123Z level=ERROR service=payment-service latency_ms=5012 msg="DB connection timeout after 5000ms host=db-2"
```

- Levels: `DEBUG INFO WARN ERROR FATAL`. Error = `ERROR` or `FATAL`.
- Services: `api-gateway`, `auth-service`, `payment-service`, `inventory-service`.
- Unparseable lines are counted as `unparsed` and never crash the parser.

---

## 5. Ingestion

**Tailer (`tailer.py`)**
- Opens the file, seeks to end (or start, when `TAIL_FROM_START=true`), and polls every `TAIL_POLL_MS` (default 200 ms).
- Keeps a byte offset and a buffer for partial lines (a line is emitted only after `\n`).
- **Truncation:** if file size < offset, reset offset to 0.
- **Rotation:** if the inode changes (or the file disappears and reappears), drain the old handle, then reopen the new file from offset 0.
- File I/O runs via `asyncio.to_thread` or small non-blocking reads. It must never block the event loop.

---

## 6. Detection

### 6.1 Sliding window
- Bucket size `BUCKET_SECONDS=5`, window `WINDOW_SECONDS=60` (12 buckets), kept per service plus a global `*` key.
- Each bucket stores total, errors, latencies (for p95), and a count per signature.
- The window is keyed on event timestamp, not arrival time. Late events older than the window are dropped.
- **Evaluation tick:** every `BUCKET_SECONDS`, a background task evaluates each window.

### 6.2 Baseline (`baseline.py`)
- Keeps the history of the last `BASELINE_POINTS=60` evaluated values (about 5 minutes) per (service, metric).
- Center = **median**, spread = **MAD** (median absolute deviation).
- **Robust z** = `0.6745 * (x − median) / max(MAD, MAD_FLOOR)`, where `MAD_FLOOR` prevents division by near-zero on very stable streams.
- Values that were flagged anomalous are **not** added to the baseline, so incidents cannot poison it.
- **Warm-up:** no alerts until `WARMUP_POINTS=12` samples (about 60 s) exist. The UI shows a "Learning baseline" state.

### 6.3 Detectors (`detectors.py`)

| Detector | Signal | Fires when |
|---|---|---|
| `error_rate` | errors ÷ total in window | robust z ≥ 3 **and** window total ≥ `MIN_VOLUME` (20) **and** absolute rise ≥ `MIN_ABS_DELTA` (2 percentage points) |
| `latency` | p95 latency_ms in window | robust z ≥ 3 and ≥ `MIN_VOLUME` samples |
| `silence` | seconds since the last line from a service | gap ≥ `SILENCE_SECONDS` (15) while that service's baseline volume > 0 |
| `new_signature` | Drain3 template ID first seen after warm-up, at level ERROR/FATAL | first occurrence; escalates if count ≥ 5 in window |

The volume and absolute-delta guards exist so that "1 error in 3 lines = 33%" does not page anyone.

### 6.4 Severity (`severity.py`)

| Severity | Rule |
|---|---|
| LOW | z ≥ 3 |
| MEDIUM | z ≥ 5, or a new signature seen once |
| HIGH | z ≥ 8, or a new signature seen ≥ 5 times in the window |
| CRITICAL | error rate ≥ 50%, or silence |

All thresholds live in `config.py`.

### 6.5 Alert payload (explainability)

Every alert carries: `id, ts, service, detector, severity, metric, current, baseline_median, baseline_mad, z, window_seconds, sample_lines[≤3], signature_template?`.

---

## 7. Incidents (`incidents/manager.py`)

- Key = `(service, detector)`. The first alert opens an incident. Later alerts update `peak_severity`, `peak_value`, `alert_count`, and `last_seen`.
- **Auto-resolve** after `RESOLVE_TICKS=3` consecutive normal evaluations. The resolve event includes the duration.
- **Notification cooldown:** a sink notification is sent on OPEN, on severity **escalation**, and on RESOLVE. Repeat alerts at the same severity do not notify.
- **Correlation:** incidents opened within `CORRELATION_SECONDS=20` of each other are linked (for example, a payment error spike with a payment latency spike).
- State: `OPEN → (ESCALATED)* → RESOLVED`.

---

## 8. Incident narrator (`summary/narrator.py`)

- On incident open or escalation, builds a structured context (service, detector, numbers, samples, correlated incidents).
- If `ANTHROPIC_API_KEY` is set, it asks an LLM for a two-sentence plain-English summary with a 3 s timeout. It **only** restates the numbers it was given.
- On any failure or missing key, it falls back to a deterministic template, for example: *"payment-service error rate rose to 18.4% (baseline 2.1%, z=7.9) starting 15:21:04. Top error: DB connection timeout."*
- Runs async and sends an `incident` update when ready. It never delays the alert itself.

---

## 9. Alert sinks (`sinks/`)

- `AlertSink` protocol: `async def send(event: SinkEvent) -> None`.
- `dispatcher.py` owns an `asyncio.Queue`. The worker calls sinks with up to 3 retries (exponential backoff) and logs failures. The pipeline only `put_nowait`s.
- `SNSSink`: `boto3` `publish` via `asyncio.to_thread`. The message is a short SMS-friendly text plus a JSON attribute payload.
- `CloudWatchSink`: `put_log_events` to `CW_LOG_GROUP/CW_LOG_STREAM`, creating them if missing.
- `ConsoleSink`: always on.
- `DRY_RUN=true` (default) logs what *would* be sent. Missing credentials disable AWS sinks gracefully; they never crash startup.

---

## 10. API

**REST**

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | status, warm-up state, lines/sec, sinks enabled |
| GET | `/api/snapshot` | current metrics, last N points per series, open incidents, recent alerts |
| GET | `/api/incidents?status=open\|resolved` | incident list |
| GET | `/api/alerts?limit=50` | recent alerts |
| POST | `/api/chaos/{scenario}` | `db_outage`, `latency_spike`, `unknown_crash`, `silence`, `rotate_log`, `recover` |
| GET | `/api/config` | effective thresholds (for the UI and the slides) |

**WebSocket `/ws`**: server → client JSON envelope `{ "type": ..., "data": ... }`

| type | when | data |
|---|---|---|
| `snapshot` | on connect | same as `/api/snapshot` |
| `metrics` | every tick | per-service `{error_rate, p95, volume, baseline_median, baseline_band:[lo,hi], warming_up}` |
| `alert` | alert emitted | Alert |
| `incident` | open / escalate / resolve / summary ready | Incident |
| `chaos` | scenario started or ended | `{scenario, active}` |

The client reconnects with backoff and re-syncs from `snapshot`. The server sends a `ping` every 20 s.

---

## 11. Generator and chaos scenarios

Baseline traffic: about 40 lines/sec across 4 services, ~1–3% errors, latency drawn from a lognormal distribution (p95 around 180 ms), and mild jitter so the baseline has real variance.

| Scenario | Effect | Duration |
|---|---|---|
| `db_outage` | payment-service errors rise to ~35% with DB timeout messages | 45 s |
| `latency_spike` | api-gateway p95 rises to ~2 s, errors unchanged | 45 s |
| `unknown_crash` | auth-service emits a never-seen FATAL signature | 30 s |
| `silence` | inventory-service stops logging | 30 s |
| `rotate_log` | renames app.log and starts a new file (proves rotation handling) | instant |
| `recover` | ends all scenarios | instant |

---

## 12. Frontend design (Apple-style)

- **Type:** `-apple-system, BlinkMacSystemFont, "SF Pro Display", "Inter", system-ui`. Large, tight-tracked numerals for metrics; restrained weights (600 for headlines, 400 for body).
- **Color (light / dark):** background `#F5F5F7` / `#000000`; surface `#FFFFFF` / `#1C1C1E`; primary text `#1D1D1F` / `#F5F5F7`; secondary `#6E6E73` / `#98989D`; accent `#0071E3`.
- **Severity:** LOW `#0A84FF`, MEDIUM `#FF9F0A`, HIGH `#FF453A`, CRITICAL `#FF375F` with a soft pulse.
- **Surfaces:** 20–24 px radius, hairline borders, very soft shadows, and a frosted-glass nav (`backdrop-filter: blur(20px) saturate(180%)`).
- **Motion:** Framer Motion springs; alerts slide and fade in; numbers animate between values; `prefers-reduced-motion` is respected.
- **Layout:**
  - Glass nav with the product name and a status pill ("All systems normal", "Learning baseline", or "2 open incidents").
  - Four metric cards: error rate, p95 latency, lines/sec, open incidents.
  - Large live chart: error rate line with a shaded baseline band and anomaly dots; a service switcher as a segmented control.
  - Right column: alert feed. Below it: incident cards.
  - Chaos Panel: a row of pill buttons with active-state indicators.
  - Incident sheet (bottom sheet on mobile, side sheet on desktop): the "why" numbers, sample lines, summary, and timeline.
- Fully responsive down to 375 px width. No emojis in the UI.

---

## 13. Replay and evaluation (`scripts/replay_loghub.py`)

- Replays the Loghub HDFS sample (which has block-level anomaly labels) into the log file at accelerated speed.
- Maps alerts back to labeled anomalous blocks within the alert window and reports precision, recall, and F1.
- Output is a small markdown table for the deck. The honest number beats a made-up one.

---

## 14. Configuration (`.env`)

```
LOG_PATH=../data/logs/app.log
TAIL_POLL_MS=200
TAIL_FROM_START=false
BUCKET_SECONDS=5
WINDOW_SECONDS=60
BASELINE_POINTS=60
WARMUP_POINTS=12
Z_LOW=3
Z_MEDIUM=5
Z_HIGH=8
CRITICAL_ERROR_RATE=0.5
MIN_VOLUME=20
MIN_ABS_DELTA=0.02
MAD_FLOOR=0.005
SILENCE_SECONDS=15
RESOLVE_TICKS=3
CORRELATION_SECONDS=20
GENERATOR_ENABLED=true
GENERATOR_RATE=40
DRY_RUN=true
AWS_REGION=ap-south-1
SNS_TOPIC_ARN=
CW_LOG_GROUP=/sentinel/alerts
CW_LOG_STREAM=demo
ANTHROPIC_API_KEY=
```

---

## 15. Failure modes handled

| Failure | Handling |
|---|---|
| Log rotation or truncation | inode and size checks in the tailer |
| Partial line at EOF | buffered until newline |
| Cold start | warm-up, no alerts, UI shows learning state |
| Low-traffic noise | minimum volume + absolute delta guards |
| Baseline poisoning during incidents | anomalous points excluded from the baseline |
| Alert storms | incident grouping + notify only on open, escalate, resolve |
| AWS down or no credentials | queued, retried, DRY_RUN fallback, never blocks |
| LLM down or slow | 3 s timeout, template fallback |
| WebSocket drop | client reconnects and re-syncs via snapshot |
| Service goes silent | silence detector |