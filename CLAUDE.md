# CLAUDE.md — Sentinel

Real-time log anomaly detector for a hackathon (Codeathon). Read `ARCHITECTURE.md` before any change; it is the source of truth. If you need to deviate from it, say so and update it in the same change.

## Stack
- **Backend:** Python 3.11+, FastAPI, uvicorn, asyncio, pydantic v2 + pydantic-settings, drain3, boto3, httpx, pytest + pytest-asyncio
- **Frontend:** React 18 + Vite + TypeScript, Tailwind CSS, Framer Motion, Recharts, zustand
- **Cloud:** AWS SNS and CloudWatch Logs (DRY_RUN by default)

## Commands
```bash
# backend
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
pytest -q

# frontend
cd frontend && npm install && npm run dev   # http://localhost:5173, proxies /api and /ws to :8000
npm run build && npm run lint
```

## Hard rules
1. **Never block the event loop.** File reads, boto3 calls, and LLM calls go through `asyncio.to_thread` or async clients. No `time.sleep` in app code.
2. **The pipeline never waits on outputs.** Sinks consume from a queue; WebSocket broadcast failures drop that client, not the pipeline.
3. **DRY_RUN is the default.** Missing AWS credentials or an Anthropic key must never crash startup. Fall back and log once.
4. **Never commit secrets.** Only `.env.example` is committed.
5. **All thresholds live in `app/config.py`.** No magic numbers in detectors.
6. **The generator writes to the file; the detector reads the file.** Never feed generator events straight into the detector.
7. **Detection logic needs tests.** Any change to `detect/` or `incidents/` needs pytest coverage for: warm-up, a spike firing, low-volume noise not firing, baseline not poisoned by incidents, silence, new signature, incident resolve.
8. **The LLM narrator only restates provided numbers.** It must never invent causes or values; the template fallback must always work.

## Conventions
- Python: type hints everywhere, pydantic models in `app/models.py`, `ruff` style, small modules, no global mutable state outside the pipeline object.
- Timestamps: UTC ISO-8601 on the wire; the frontend formats them locally.
- WebSocket messages use the `{type, data}` envelope from ARCHITECTURE.md §10. Keep TS types in `frontend/src/types.ts` in sync with `models.py`.
- Frontend: Apple-style design per ARCHITECTURE.md §12. Use design tokens as CSS variables and support dark mode. No emojis in the UI. Respect `prefers-reduced-motion`. Mobile-first down to 375 px.
- Commit after each phase with a clear message.

## Workflow
- Work in the phases listed in the kickoff prompt. **Stop after each phase**, run tests or the dev server, and report what works, what's stubbed, and anything that deviates from the architecture.
- When unsure between two designs, choose the simpler one that still meets ARCHITECTURE.md and note it.
- Do not add features outside ARCHITECTURE.md without asking.

## Demo priorities (if time runs short, cut from the bottom)
1. Core pipeline + error-rate detection + live chart + alert feed
2. Chaos Panel
3. Explainable alerts + incident grouping and resolve
4. Silence + new-signature detection
5. SNS to phone
6. LLM narrator
7. Loghub replay with precision/recall