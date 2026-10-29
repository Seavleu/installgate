# ui/ — Jenny

Next.js app for the demo.

- `/` is live. **Terminal** streams each stage from `POST /check/stream` as it finishes, then the verdict, evidence, cited explanation, command diff, and cost receipt. Gate Off shows the command an agent would run unchecked. **Agent (MCP)** sends real JSON-RPC (`tools/list`, `tools/call check_install`) to the MCP endpoint and shows what the agent should do next.
- `/mockup` is the design mockup with sample data. Nothing there is a live verdict.

`/api/check`, `/api/check/stream`, and `/api/mcp` forward to `API_URL` (default `http://127.0.0.1:8000`). A judge can point Cursor or Claude at `<ui origin>/api/mcp`. Start the API first.

```bash
uv run uvicorn mcp_server.api:app --port 8000
cd ui && pnpm install && pnpm dev   # :3000
```

Task: T12. Hosting is T14. The offline substitute check is T15.
