# The API with its worker (T-506): one image for Render, the CI check and the offline stand (T-507).
# Build from the repository root (a uv workspace): docker build -f apps/api/Dockerfile .

FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
COPY packages/core packages/core
COPY apps/api apps/api
COPY evals/pyproject.toml evals/pyproject.toml
# only the API and the core with their runtime dependencies, installed as packages (no sources)
RUN uv sync --frozen --no-dev --package reqgraph-api --no-editable

FROM python:3.12-slim
RUN useradd --create-home --uid 10001 app
COPY --from=build /app/.venv /app/.venv
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYDANTIC_AI_NO_BANNER=1
USER app
WORKDIR /home/app
EXPOSE 8000
# the port comes from $PORT (Render), 8000 otherwise
CMD ["reqgraph-api", "serve"]
