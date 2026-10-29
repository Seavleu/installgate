FROM python:3.11-slim

WORKDIR /app
RUN pip install --no-cache-dir uv
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY contracts ./contracts
COPY engine ./engine
COPY validator ./validator
COPY router ./router
COPY remediate ./remediate
COPY mcp_server ./mcp_server
COPY eval ./eval
RUN uv sync --frozen --no-dev

# The cache volume inherits this owner the first time it is mounted.
RUN useradd --system --uid 10001 --home /app app && mkdir -p /app/.cache && chown app:app /app/.cache
USER app

ENV CACHE_PATH=/app/.cache/installgate.sqlite
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"]
CMD ["uvicorn", "mcp_server.api:app", "--host", "0.0.0.0", "--port", "8000"]
