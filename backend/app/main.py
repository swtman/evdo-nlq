"""
FastAPI application entry point.

This file's only job is to wire everything together:
  1. Configure logging for the whole process.
  2. Create the FastAPI application object.
  3. Attach CORS middleware so the browser allows frontend → backend requests.
  4. Mount the route routers so FastAPI knows about all endpoints.

All business logic lives elsewhere. This file has no imports from the LLM
layer, the pipeline, or the SPARQL client — it only needs the two API routers
and the settings object.

HOW TO RUN
----------
    cd backend
    uv run fastapi dev app/main.py

`fastapi dev` is a shortcut that calls `uvicorn app.main:app --reload` under
the hood — see the uvicorn explanation below.

TODO: add auth/rate limiting before any public deployment. Currently any
process on localhost can hit port 8000 and consume your API key quota.
CORS only blocks browsers — it does not block curl or scripts.
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.entities import router as entities_router
from app.api.providers import router as providers_router
from app.api.query import router as query_router
from app.config import settings

# ---------------------------------------------------------------------------
# LOGGING
#
# `logging.basicConfig` configures the root logger — the parent of every
# logger in the process. All modules in this project use:
#     logger = logging.getLogger(__name__)
# Those loggers inherit this configuration automatically.
#
# `level=settings.log_level` sets the minimum severity to emit. The value
# comes from LOG_LEVEL in .env (e.g. "INFO" or "DEBUG"). Changing it and
# restarting is all that's needed to increase or decrease verbosity.
#
# `%(name)s` in the format prints the logger's name — the module's __name__
# (e.g. "app.pipeline.query_pipeline") — making it easy to find which module
# produced each log line.
#
# NOTE: this call is a no-op if pytest has already attached a log handler
# before importing this module. That is expected — pytest handles its own
# log capture during tests.
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)

# ---------------------------------------------------------------------------
# APPLICATION
#
# `FastAPI(...)` creates the single application object that uvicorn will call
# into for every incoming HTTP request. `title` and `version` appear in the
# auto-generated OpenAPI docs at http://localhost:8000/docs.
#
# No `lifespan=` hook is set — there is nothing to do at startup or shutdown.
# The ontology summary is loaded lazily on the first request (module-level
# cache in ontology/loader.py), and providers are constructed per-request.
# ---------------------------------------------------------------------------
app = FastAPI(title="evdo-nlq", version="0.1.0")

# ---------------------------------------------------------------------------
# CORS MIDDLEWARE
#
# WHAT IS CORS?
# Browsers enforce the Same-Origin Policy: JavaScript running on
# http://localhost:5173 (the React frontend) is forbidden from making HTTP
# requests to http://localhost:8000 (this backend), because the port numbers
# differ — a different port means a different "origin."
#
# CORS (Cross-Origin Resource Sharing) is the official mechanism to relax
# that restriction. When the frontend JavaScript makes a cross-origin request,
# the browser first sends a preflight OPTIONS request: "Backend, do you allow
# requests from http://localhost:5173?" The CORSMiddleware replies with the
# appropriate Access-Control-Allow-Origin header. The browser then allows the
# real request through.
#
# WITHOUT THIS MIDDLEWARE: the browser would block every response from the
# backend before JavaScript could read it. The backend would still receive the
# requests (CORS is browser-enforced, not server-enforced), but the frontend
# would silently fail with a "CORS error" in the browser's developer console.
#
# `allow_origins=[settings.frontend_origin]`
#   Only the exact origin in .env (default: http://localhost:5173) is
#   whitelisted. Note: "http://" and "https://" are different origins — if the
#   frontend moves to HTTPS, FRONTEND_ORIGIN in .env must be updated to match.
#
# `allow_methods=["*"]` — all HTTP methods (GET, POST, OPTIONS, …) are allowed.
# `allow_headers=["*"]` — all headers are allowed (e.g. Content-Type: application/json).
#   Without this, sending Content-Type in a POST body would be blocked.
#
# `allow_credentials` is not set (defaults to False). Cookies and Authorization
# headers are not needed — this project has no auth.
#
# This middleware wraps every request before it reaches any route handler.
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# ROUTERS
#
# Routes defined in providers.py and query.py are attached to APIRouter
# objects, not to `app` directly. `include_router` registers all of a
# router's routes onto the main app.
#
# No `prefix` is passed, so routes are mounted exactly as declared:
#   query_router     → POST /query, POST /query/stream
#   providers_router → GET  /providers
#
# The `as` aliases in the imports (router as query_router, etc.) are needed
# because both files export a variable named `router` — without aliasing,
# the second import would overwrite the first in this module's namespace.
#
# WHAT IS uvicorn?
# FastAPI is a framework — it defines how requests are processed but cannot
# listen on a TCP port by itself. uvicorn is the ASGI server that listens on
# port 8000, accepts HTTP connections, and calls into `app` for each request.
#
# `fastapi dev app/main.py` is a shortcut that runs:
#     uvicorn app.main:app --reload
#   - `app.main` — the Python module path to this file
#   - `:app`     — the name of the FastAPI object inside the module
#   - `--reload` — restart the server automatically on file changes
#
# On each hot-reload, Python re-imports this module: logging is reconfigured,
# `FastAPI()` is re-created, and `settings` is re-read from .env. This means
# changing .env and saving any source file will pick up the new values.
#
# entities_router → GET /entities/search (course/book title search, shared
# with the SPARQL grounding pipeline — see app/api/entities.py)
# ---------------------------------------------------------------------------
app.include_router(query_router)
app.include_router(providers_router)
app.include_router(entities_router)
