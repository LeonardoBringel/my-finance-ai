FROM python:3.13-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.13.0 /uv /usr/local/bin/uv

# Non-root user
RUN useradd -m -u 1000 appuser

WORKDIR /app

# Copy dependency files first (layer caching)
COPY pyproject.toml uv.lock ./

# Install third-party dependencies only; the project itself needs src/
RUN uv sync --frozen --no-dev --no-install-project

# Copy application code
COPY --chown=appuser:appuser . .

# Install the project itself
RUN uv sync --frozen --no-dev

ARG APP_VERSION=latest
ENV APP_VERSION=${APP_VERSION}
ENV PATH="/app/.venv/bin:${PATH}"
RUN echo "${APP_VERSION}" > /app/.version

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=5)" || exit 1

CMD ["uvicorn", "my_finance_ai.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
