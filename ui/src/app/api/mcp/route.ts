import { NextResponse } from "next/server";
import { forward } from "../forward";

export const dynamic = "force-dynamic";

const LOOPBACK = /^(localhost|127\.0\.0\.1)(:\d+)?$/i;

function advertisedOrigin(request: Request): string | null {
  const env = (process.env.PUBLIC_SITE_URL || process.env.NEXT_PUBLIC_SITE_URL || "").replace(/\/$/, "");
  if (env) {
    try {
      if (!LOOPBACK.test(new URL(env).host)) return env;
    } catch {
      return env;
    }
  }
  const host = (request.headers.get("x-forwarded-host") || request.headers.get("host") || "")
    .split(",")[0]
    .trim();
  if (!host || LOOPBACK.test(host)) return null;
  const proto = request.headers.get("x-forwarded-proto") || "https";
  return `${proto}://${host}`;
}

export function POST(request: Request) {
  return forward(request, "/mcp");
}

export function GET(request: Request) {
  const accept = request.headers.get("accept") ?? "";
  if (accept.includes("text/event-stream")) {
    return forward(request, "/mcp");
  }
  const origin = advertisedOrigin(request);
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
