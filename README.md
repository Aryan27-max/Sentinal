# Sentinel

Real-time log anomaly detector. It tails a growing log file, keeps a rolling error rate and a robust baseline per service, raises explainable alerts with severity levels, groups them into incidents that auto-resolve, streams everything to a live dashboard over WebSockets, and pushes notifications to AWS SNS and CloudWatch Logs.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the design and [CLAUDE.md](CLAUDE.md) for the working rules.

> Work in progress. Setup, the config table, and the demo script land in Phase 10.

## Quickstart

Requires Python 3.11+ and Node 20+.

```bash
cp .env.example .env        # DRY_RUN=true by default; no AWS credentials needed

# backend (http://localhost:8000)
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows (Git Bash): source .venv/Scripts/activate
                            # Windows (PowerShell): .venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
pytest -q

# frontend (http://localhost:5173, proxies /api and /ws to :8000)
cd frontend
npm install
npm run dev
```
