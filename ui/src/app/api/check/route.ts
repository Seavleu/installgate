import { forward } from "../forward";

export const dynamic = "force-dynamic";

export function POST(request: Request) {
  return forward(request, "/check");
}
