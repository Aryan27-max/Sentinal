# Sentinel

Real-time log anomaly detector. Sentinel tails a growing log file and keeps a rolling 60 s error rate and p95 latency per service. It learns a robust baseline (median + MAD) and raises explainable alerts with severity levels. Alerts stream to a live dashboard over WebSockets and go to AWS SNS and CloudWatch Logs.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full design and [CLAUDE.md](CLAUDE.md) for the working rules.

## Run it

Requires Python 3.11+ and Node 20+. Use two terminals.

**Backend** (http://127.0.0.1:8000)

```bash
cd backend
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# Windows Git Bash:   source .venv/Scripts/activate
# macOS / Linux:      source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --port 8000
```

**Frontend** (http://localhost:5173, proxies `/api` and `/ws` to the backend)

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. For the first ~60 s the status pill reads **Learning baseline**. After that, press a Chaos Panel button.

**Tests**

```bash
cd backend && pytest -q                    # tailer, parser, detectors, WS snapshot
cd frontend && npm run build && npm run lint
```

## What happens

```
generator ──writes──▶ data/logs/app.log ──▶ tailer ──▶ parser ──▶ detector ──▶ WebSocket /ws ──▶ dashboard
                                                                     └──▶ sink queue ──▶ console / SNS / CloudWatch
```

- **Generator** (`app/generator.py`) appends about 40 lines/s across 4 services, with about 2% errors and lognormal latency (p95 around 180 ms).
- **Tailer** (`app/tailer.py`) runs stat → open → seek → read → close every 200 ms. It buffers partial lines and survives truncation and rotation.
- **Detector** (`app/detector.py`) keeps 5 s buckets over a 60 s window per service. Each metric is scored with `z = 0.6745 · (x − median) / MAD` against the last 60 normal values.
  - An alert needs z ≥ 3, window volume ≥ 20 and a rise of at least 2 percentage points. The latest 15 s must also still be elevated, so alerts stop about 15 s after recovery.
  - Anomalous values never enter the baseline, and nothing alerts during the 12-point (about 60 s) warm-up.
  - Silence (a service logs nothing for 15 s) is CRITICAL.
  - Severity: z ≥ 3 is LOW, ≥ 5 MEDIUM, ≥ 8 HIGH, and an error rate ≥ 50% is CRITICAL.
  - Each (service, detector) pair alerts at most once per 30 s, but an escalation in severity always gets through.
- **Sinks** (`app/sinks.py`) run off an asyncio queue with 3 retries and backoff. With `DRY_RUN=true` (the default) or missing AWS credentials, they log the exact SNS and CloudWatch payloads instead of sending.

## Chaos scenarios

| Button | Effect | Detector that fires |
|---|---|---|
| DB outage | payment-service errors rise to ~35% for 45 s | error rate: LOW → MEDIUM → HIGH within ~15 s |
| Latency spike | api-gateway p95 rises to ~2 s for 45 s | latency: HIGH within ~5 s |
| Silence | inventory-service stops logging for 30 s | silence: CRITICAL after ~15–20 s |
| Recover | ends every scenario | — |

## Real SNS / CloudWatch

Copy `.env.example` to `.env` at the repo root and set `DRY_RUN=false`, `SNS_TOPIC_ARN=...`, and `AWS_REGION`. Credentials come from the standard AWS chain (env vars, `~/.aws/credentials`, or SSO). For SMS, subscribe your phone number to the topic. Each message is under 160 characters, for example `Sentinel HIGH: payment-service error rate 18.4% vs 1.8% z=11.1`.

## API

| Method | Path | |
|---|---|---|
| GET | `/api/health` | status, warm-up, lines/sec, sink modes |
| GET | `/api/snapshot` | latest metrics, chart history, recent alerts |
| GET | `/api/alerts?limit=50` | recent alerts |
| POST | `/api/chaos/{db_outage,latency_spike,silence,recover}` | start a scenario |
| WS | `/ws` | `snapshot` on connect, then `metrics` every 5 s, `alert`, `chaos`, `ping` |
