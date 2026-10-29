import { forward } from "../forward";

export const dynamic = "force-dynamic";

export function POST(request: Request) {
  return forward(request, "/mcp");
}

export function GET(request: Request) {
  return forward(request, "/mcp");
}

export function DELETE(request: Request) {
  return forward(request, "/mcp");
}
