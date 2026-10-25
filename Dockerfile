FROM python:3.11-slim

WORKDIR /app
RUN pip install --no-cache-dir uv
COPY pyproject.toml README.md LICENSE ./
COPY contracts ./contracts
COPY engine ./engine
COPY validator ./validator
COPY router ./router
COPY remediate ./remediate
COPY mcp_server ./mcp_server
COPY eval ./eval
RUN uv sync --no-dev

ENV CACHE_PATH=/app/.cache/installgate.sqlite
EXPOSE 8000
# Jenny: point this at mcp_server.api:app once the FastAPI app exists
CMD ["python", "-c", "print('Fill mcp_server/api.py first. See mcp_server/README.md')"]
