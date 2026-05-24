FROM python:3.12-slim

# Install uv (the package manager this project uses)
RUN pip install uv --no-cache-dir

WORKDIR /app

# Copy dependency manifests first so Docker layer-caches them.
# uv.lock + pyproject.toml define the exact dependency set.
COPY pyproject.toml uv.lock ./

# Install production deps only (no test/dev extras).
# --frozen: fail if uv.lock is not up to date.
# --no-dev: skip dependency groups marked [tool.uv.dev].
RUN uv sync --frozen --no-dev

# Copy application source.
COPY app/ ./app/

# Expose the port uvicorn will listen on.
EXPOSE 8000

# Run uvicorn directly (no reload — this is the production image).
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
