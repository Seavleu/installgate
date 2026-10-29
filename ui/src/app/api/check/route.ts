import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const api = process.env.API_URL ?? "http://127.0.0.1:8000";
  let target: URL;
  try {
    target = new URL("/check", api.endsWith("/") ? api : `${api}/`);
  } catch {
    return NextResponse.json({ detail: "API_URL is not a URL." }, { status: 502 });
  }

  const headers = new Headers({ "Content-Type": "application/json" });
  const forwarded = request.headers.get("x-forwarded-for");
  if (forwarded) headers.set("x-forwarded-for", forwarded);

  try {
    const response = await fetch(target, {
      method: "POST",
      headers,
      body: await request.text(),
      cache: "no-store",
    });
    const out = new NextResponse(await response.text(), {
      status: response.status,
      headers: { "Content-Type": response.headers.get("Content-Type") ?? "application/json" },
    });
    const spend = response.headers.get("x-installgate-spend");
    if (spend) out.headers.set("x-installgate-spend", spend);
    return out;
  } catch {
    return NextResponse.json({ detail: "The check API is not running." }, { status: 502 });
  }
}
