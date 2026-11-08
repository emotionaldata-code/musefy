FROM ghcr.io/astral-sh/uv:0.11.7 AS uv
FROM python:3.13-slim
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 PATH="/app/.venv/bin:$PATH"
COPY pyproject.toml uv.lock .python-version ./
COPY packages/core ./packages/core
COPY packages/backend ./packages/backend
COPY packages/scraper ./packages/scraper
COPY packages/cli ./packages/cli
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --all-packages --no-dev --no-editable
COPY alembic.ini ./
COPY migrations ./migrations
ENV HF_HOME=/opt/models TOKENIZERS_PARALLELISM=false
RUN --mount=type=cache,target=/opt/models/xet musefy embedding-model
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
RUN useradd --create-home app
USER app
CMD ["uvicorn", "musefy_backend.app:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
