import { NextResponse } from "next/server";
import { forward } from "../forward";

export const dynamic = "force-dynamic";

const LOOPBACK = /^(localhost|127\.0\.0\.1)(:\d+)?$/i;
const SITE = "https://installgate.installgate-ui.workers.dev";

function advertisedOrigin(): string {
  const env = (process.env.PUBLIC_SITE_URL || process.env.NEXT_PUBLIC_SITE_URL || "").replace(/\/$/, "");
  if (env) {
    try {
      const host = new URL(env).host;
      if (!LOOPBACK.test(host) && !host.endsWith("trycloudflare.com")) return env;
    } catch {
      return SITE;
    }
  }
  return SITE;
}

export function POST(request: Request) {
  return forward(request, "/mcp");
}

export function GET(request: Request) {
  const accept = request.headers.get("accept") ?? "";
  if (accept.includes("text/event-stream")) {
    return forward(request, "/mcp");
  }
  const origin = advertisedOrigin();
  return NextResponse.json({
    name: "installgate",
    tool: "check_install",
    transport: "MCP Streamable HTTP",
    ui: "/",
    url: origin ? `${origin}/api/mcp` : null,
    hint: origin
      ? "Point Cursor or Claude at url. POST JSON-RPC. This is not a web page."
      : "Set PUBLIC_SITE_URL to the https host agents should call. localhost is not reachable from Claude.",
  });
}

export function DELETE(request: Request) {
  return forward(request, "/mcp");
}
