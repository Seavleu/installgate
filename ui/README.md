# ui/ — Jenny

Next.js app for the demo.

Show: Gate OFF vs Gate ON, evidence list, cited explanation, command diff, cost receipt.

The page calls `/api/check`. That route forwards to `API_URL` (default `http://127.0.0.1:8000`). Start the API first.

```bash
uv run uvicorn mcp_server.api:app --port 8000
cd ui && pnpm install && pnpm dev   # :3000
```

Task: T12. Hosting is T14. The offline substitute check is T15.
