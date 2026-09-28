import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket

log = logging.getLogger("sentinel.ws")

SEND_TIMEOUT_SECONDS = 1.0


class Hub:
    """Tracks WebSocket clients. A slow or dead client is dropped; it never stalls the pipeline."""

    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()

    async def connect(self, ws: WebSocket, snapshot: dict[str, Any]) -> None:
        await ws.accept()
        await ws.send_text(json.dumps({"type": "snapshot", "data": snapshot}))
        self.clients.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self.clients.discard(ws)

    async def broadcast(self, type_: str, data: Any) -> None:
        if not self.clients:
            return
        text = json.dumps({"type": type_, "data": data})
        dead: list[WebSocket] = []

        async def send(ws: WebSocket) -> None:
            try:
                await asyncio.wait_for(ws.send_text(text), SEND_TIMEOUT_SECONDS)
            except Exception:
                dead.append(ws)

        await asyncio.gather(*(send(ws) for ws in list(self.clients)))
        for ws in dead:
            self.clients.discard(ws)
            log.info("Dropped unresponsive WebSocket client")
