# dev.ps1 — start the backend dev server with this project's required flags.
#
# Usage (from anywhere):   .\backend\dev.ps1        or, inside backend\:   .\dev.ps1
# Extra arguments are passed through to `fastapi dev`, e.g.  .\dev.ps1 --host 0.0.0.0
#
# Why a script: `fastapi dev` has no project setting for these flags, and forgetting
# either one fails quietly (see backend/CLAUDE.md, "Dev-server gotchas"):
#   --port 8001        The Vite proxy (frontend/vite.config.ts), nginx and Docker all
#                      target 8001. Port 8000 is also held by Splunk's splunkd on this
#                      machine (0.0.0.0:8000); uvicorn's 127.0.0.1:8000 bind coexists with
#                      it silently and some requests land on Splunk.
#   --reload-dir app   Watch only app/, not all of backend/ — otherwise every file the
#                      LLM DiskCache writes to backend/.llm_cache/ restarts the server
#                      mid-request.
# PYTHONIOENCODING=utf-8 stops the startup banner's emoji from crashing a console that
# is not in UTF-8 (UnicodeEncodeError: 'charmap' codec can't encode character).

$ErrorActionPreference = 'Stop'
$env:PYTHONIOENCODING = 'utf-8'

Push-Location $PSScriptRoot   # run from backend\ whatever the caller's directory
try {
    uv run fastapi dev app/main.py --reload-dir app --port 8001 @args
}
finally {
    Pop-Location
}
