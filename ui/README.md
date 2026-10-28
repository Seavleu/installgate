# ui/ — Jenny

Next.js app for the demo.

Show: Gate OFF vs Gate ON, evidence list, cited explanation, command diff, cost receipt.

The page calls `/api/check`, which Next forwards to the API. Start the API first.

```bash
uv run uvicorn mcp_server.api:app --port 8000
cd ui && pnpm install && pnpm dev   # :3000
```

Task: T12. Hosting is T14. The offline substitute check is T15.
