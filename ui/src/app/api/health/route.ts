import { forward } from "../forward";

export const dynamic = "force-dynamic";

export function GET(request: Request) {
  return forward(request, "/health");
}
