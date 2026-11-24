"""FastAPI application: REST API, live dashboard WebSocket and voice call WebSocket.

Run from backend/:  uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.config import get_settings
from app.database import init_db
from app.services.errors import DomainError
from app.services.events import bus
from app.voice.agent import handle_call

settings = get_settings()
logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    bus.bind_loop(asyncio.get_running_loop())
    logger.info(
        "Started: voice_mode=%s db=%s%s", settings.effective_voice_mode, settings.database_path,
        f" (missing keys: {', '.join(settings.missing_live_keys)})"
        if settings.effective_voice_mode == "mock" else "",
    )
    yield


app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
app.include_router(router)


@app.exception_handler(DomainError)
async def domain_error_handler(_request: Request, exc: DomainError):
    return JSONResponse(status_code=exc.http_status, content={"error": exc.to_dict()})


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_request: Request, exc: RequestValidationError):
    first = exc.errors()[0] if exc.errors() else {}
    field = ".".join(str(p) for p in first.get("loc", [])[1:])
    return JSONResponse(status_code=422, content={"error": {
        "code": "invalid_request", "message": f"{field}: {first.get('msg', 'invalid value')}",
    }})


@app.exception_handler(Exception)
async def unhandled_error_handler(_request: Request, exc: Exception):
    logger.exception("Unhandled error", exc_info=exc)
    return JSONResponse(status_code=500, content={"error": {
        "code": "internal_error", "message": "An unexpected error occurred.",
    }})


@app.websocket("/ws/dashboard")
async def dashboard_events(websocket: WebSocket) -> None:
    """Pushes appointment.booked / appointment.cancelled events to dashboards."""
    await websocket.accept()
    queue = bus.subscribe()
    try:
        await websocket.send_json({"type": "hello"})
        while True:
            event = await queue.get()
            await websocket.send_json(event)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        bus.unsubscribe(queue)


@app.websocket("/ws/call")
async def voice_call(websocket: WebSocket) -> None:
    """One browser call. Audio + JSON events; see app/voice/serializer.py."""
    await websocket.accept()
    await handle_call(websocket)
