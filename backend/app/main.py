import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.config import get_settings
from app.pipeline import Sentinel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("sentinel")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    sentinel = Sentinel(settings)
    app.state.sentinel = sentinel
    log.info("Sentinel starting; tailing %s", settings.resolved_log_path)
    await sentinel.start()
    yield
    await sentinel.stop()
    log.info("Sentinel stopped")


app = FastAPI(title="Sentinel", lifespan=lifespan)
app.include_router(router)

# In production (Docker / Railway) the built dashboard is served from the same origin as /api
# and /ws. In development Vite serves it instead, so the folder may not exist.
_static_dir = get_settings().resolved_static_dir
if _static_dir.is_dir():
    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="dashboard")
