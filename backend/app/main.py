"""
FastAPI application entry point.

This file's only job is to wire everything together:
  1. Configure logging for the whole process.
  2. Create the FastAPI application object.
  3. Attach CORS middleware so the browser allows frontend → backend requests.
  4. Mount the route routers so FastAPI knows about all endpoints.

All business logic lives elsewhere. This file has no imports from the LLM
layer, the pipeline, or the SPARQL client. It only needs the two API routers
and the settings object.

HOW TO RUN
----------
    cd backend
    uv run fastapi dev app/main.py


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
# `logging.basicConfig` configures the root logger, the parent of every
# logger in the process. All modules in this project use:
#     logger = logging.getLogger(__name__)
# Those loggers inherit this configuration automatically.
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    force=True,
)

# ---------------------------------------------------------------------------
# APPLICATION
#
# `FastAPI(...)` creates the single application object that uvicorn will call
# into for every incoming HTTP request. 
#
# No `lifespan=` hook is set — there is nothing to do at startup or shutdown.
# The ontology summary is loaded lazily on the first request (module-level
# cache in ontology/loader.py), and providers are constructed per-request.
# ---------------------------------------------------------------------------
app = FastAPI(title="evdo-nlq", version="0.1.0")

# ---------------------------------------------------------------------------
# Cross-Origin Resource Sharing (CORS) Configuration
#
# Scoped strictly to `settings.frontend_origin` to prevent arbitrary origin
# access. Methods and headers are open (`*`) to support standard REST ops
# and custom payload headers (e.g., Content-Type).
#
# `allow_credentials` defaults to False: auth tokens/cookies are currently not used.
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
# Sub-routers are mounted directly to root (no prefixes applied).
# - query_router:    /query, /query/stream
# - providers_router: /providers
# - entities_router:  /entities/search, /entities/list 
# ---------------------------------------------------------------------------
app.include_router(query_router)
app.include_router(providers_router)
app.include_router(entities_router)
