from typing import Any

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect

from app.generator import SCENARIOS
from app.pipeline import Sentinel

router = APIRouter()


def sentinel(request: Request) -> Sentinel:
    return request.app.state.sentinel


@router.get("/api/health")
async def health(request: Request) -> dict[str, Any]:
    return sentinel(request).health()


@router.get("/api/snapshot")
async def snapshot(request: Request) -> dict[str, Any]:
    return sentinel(request).snapshot()


@router.get("/api/alerts")
async def alerts(request: Request, limit: int = 50) -> list[dict[str, Any]]:
    return [a.model_dump(mode="json") for a in list(sentinel(request).alerts)[:limit]]


@router.post("/api/chaos/{scenario}")
async def chaos(request: Request, scenario: str) -> dict[str, Any]:
    if scenario not in SCENARIOS and scenario != "recover":
        raise HTTPException(404, f"unknown scenario {scenario!r}")
    app = sentinel(request)
    result = app.chaos(scenario)
    await app.hub.broadcast("chaos", {**result, "active_scenarios": app.generator.active()})
    return result


@router.websocket("/ws")
async def ws(websocket: WebSocket) -> None:
    app: Sentinel = websocket.app.state.sentinel
    await app.hub.connect(websocket, app.snapshot())
    try:
        while True:
            await websocket.receive_text()  # clients don't send anything; this detects disconnects
    except WebSocketDisconnect:
        pass
    finally:
        app.hub.disconnect(websocket)
