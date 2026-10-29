import { NextResponse } from "next/server";

const PASS_IN = ["content-type", "accept", "mcp-protocol-version", "mcp-session-id", "x-forwarded-for"];
const PASS_OUT = ["content-type", "cache-control", "mcp-session-id", "x-installgate-spend"];

export async function forward(request: Request, path: string): Promise<Response> {
  const api = process.env.API_URL ?? "http://127.0.0.1:8000";
  let target: URL;
  try {
    target = new URL(path, api.endsWith("/") ? api : `${api}/`);
  } catch {
    return NextResponse.json({ detail: "API_URL is not a URL." }, { status: 502 });
  }

  const headers = new Headers();
  for (const name of PASS_IN) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }

  try {
    const hasBody = request.method !== "GET" && request.method !== "HEAD";
    const response = await fetch(target, {
      method: request.method,
      headers,
      body: hasBody ? await request.text() : undefined,
      cache: "no-store",
    });
    const out = new Headers();
    for (const name of PASS_OUT) {
      const value = response.headers.get(name);
      if (value) out.set(name, value);
    }
    return new Response(response.body, { status: response.status, headers: out });
  } catch {
    return NextResponse.json({ detail: "The check API is not running." }, { status: 502 });
  }
}
