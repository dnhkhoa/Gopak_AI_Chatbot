from __future__ import annotations

import logging
import os
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api import routes_artifacts, routes_chat, routes_conversations, routes_data, routes_health
from src.config import _load_dotenv, ROOT


_load_dotenv(ROOT / ".env")
logger = logging.getLogger("gopak.web")


def create_app() -> FastAPI:
    app = FastAPI(title="Gopak API", version="0.1.0")
    frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[frontend_origin, "http://127.0.0.1:5173"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid4())
        started = perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("request failed", extra={"request_id": request_id, "path": request.url.path})
            return JSONResponse(status_code=500, content={"detail": "Internal server error", "request_id": request_id})
        elapsed = round((perf_counter() - started) * 1000, 1)
        logger.info("%s %s %s %.1fms", request.method, request.url.path, response.status_code, elapsed)
        response.headers["x-request-id"] = request_id
        return response

    app.include_router(routes_health.router)
    app.include_router(routes_conversations.router)
    app.include_router(routes_chat.router)
    app.include_router(routes_artifacts.router)
    app.include_router(routes_data.router)
    return app


app = create_app()
