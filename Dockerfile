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

ENV CACHE_PATH=/app/.cache/installgate.sqlite
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "mcp_server.api:app", "--host", "0.0.0.0", "--port", "8000"]
