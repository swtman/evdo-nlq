"""FastAPI application entry point.

Run with: uv run fastapi dev app/main.py
TODO: future — add auth/rate limiting before any public deployment.
"""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.providers import router as providers_router
from app.api.query import router as query_router
from app.config import settings

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)

app = FastAPI(title="evdo-nlq", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(query_router)
app.include_router(providers_router)
