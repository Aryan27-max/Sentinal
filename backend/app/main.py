import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("sentinel")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    log.info("Sentinel starting; log file %s", settings.resolved_log_path)
    # Pipeline tasks (generator, tailer, tick loop, sink dispatcher) start here in Phase 3.
    yield
    log.info("Sentinel stopped")


app = FastAPI(title="Sentinel", lifespan=lifespan)
app.include_router(router)
