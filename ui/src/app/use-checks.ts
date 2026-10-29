"use client";

import { useRef, useState } from "react";
import { GateVerdict } from "@contracts";
import { stripNulls, type Tone } from "./terminal";

export type StageEvent = { stage: string; status: Tone; detail: string; ms: number };
export type Frame = { dir: "→" | "←"; title: string; body: string; bad?: boolean };

function httpError(status: number): string {
  if (status === 429) return "This demo is limited to a few checks a minute. Wait and try again.";
  if (status === 404 || status === 502) return "The check API is not running on port 8000.";
  return `The check returned HTTP ${status}.`;
}

function parseVerdict(value: unknown): GateVerdict | null {
  const parsed = GateVerdict.safeParse(stripNulls(value));
  return parsed.success ? parsed.data : null;
}

export type StreamState = {
  command: string | null;
  gateOff: boolean;
  events: StageEvent[];
  raw: string[];
  verdict: GateVerdict | null;
  spendCapped: boolean;
  error: string | null;
  pending: boolean;
  elapsedMs: number;
};

const EMPTY_STREAM: StreamState = {
  command: null,
  gateOff: false,
  events: [],
  raw: [],
  verdict: null,
  spendCapped: false,
  error: null,
  pending: false,
  elapsedMs: 0,
};

/** POST /check/stream: one NDJSON line per finished stage, then the verdict. */
export function useStreamCheck() {
  const [state, setState] = useState<StreamState>(EMPTY_STREAM);
  const busy = useRef(false);

  function handle(line: string) {
    let msg: { type?: string; verdict?: unknown; spend_capped?: boolean; detail?: string } & Partial<StageEvent>;
    try {
      msg = JSON.parse(line);
    } catch {
      return;
    }
    setState((s) => {
      const next = { ...s, raw: [...s.raw, line] };
      if (msg.type === "stage") next.events = [...s.events, msg as StageEvent];
      if (msg.type === "error") next.error = msg.detail ?? "The check failed. Treat it as a review.";
      if (msg.type === "verdict") {
        next.verdict = parseVerdict(msg.verdict);
        next.spendCapped = !!msg.spend_capped;
        if (!next.verdict) next.error = "The check returned a verdict this screen does not recognise.";
      }
      return next;
    });
  }

  async function run(command: string) {
    if (busy.current) return;
    busy.current = true;
    setState({ ...EMPTY_STREAM, command, pending: true });
    const started = performance.now();
    let error: string | null = null;
    try {
      const response = await fetch("/api/check/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command }),
      });
      if (!response.ok || !response.body) {
        error = httpError(response.status);
      } else {
        const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
        let buffer = "";
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += value;
          const lines = buffer.split("\n");
          buffer = lines.pop() ?? "";
          lines.filter((l) => l.trim()).forEach(handle);
        }
        if (buffer.trim()) handle(buffer);
      }
    } catch {
      error = "The check API is not running on port 8000.";
    } finally {
      busy.current = false;
      setState((s) => ({
        ...s,
        pending: false,
        elapsedMs: performance.now() - started,
        error: error ?? s.error ?? (s.verdict ? null : "The stream ended without a verdict. Treat it as a review."),
      }));
    }
  }

  function skip(command: string) {
    setState({ ...EMPTY_STREAM, command, gateOff: true });
  }

  function restore(next: StreamState) {
    if (busy.current) return;
    setState({ ...next, pending: false });
  }

  return { state, run, skip, restore };
}

type McpState = {
  command: string | null;
  frames: Frame[];
  verdict: GateVerdict | null;
  raw: unknown;
  error: string | null;
  pending: boolean;
  elapsedMs: number;
};

const EMPTY_MCP: McpState = { command: null, frames: [], verdict: null, raw: null, error: null, pending: false, elapsedMs: 0 };

/** Real JSON-RPC to the check_install tool over MCP Streamable HTTP. */
export function useMcpCheck() {
  const [state, setState] = useState<McpState>(EMPTY_MCP);
  const busy = useRef(false);
  const push = (frame: Frame) => setState((s) => ({ ...s, frames: [...s.frames, frame] }));

  async function rpc(id: number, method: string, params?: Record<string, unknown>) {
    const body = { jsonrpc: "2.0", id, method, ...(params ? { params } : {}) };
    push({ dir: "→", title: `POST /api/mcp · ${method}${params ? ` ${String(params.name)}` : ""}`, body: JSON.stringify(body) });
    const started = performance.now();
    const response = await fetch("/api/mcp", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json, text/event-stream" },
      body: JSON.stringify(body),
    });
    const json: unknown = await response.json().catch(() => null);
    return { response, json, ms: Math.round(performance.now() - started) };
  }

  async function run(command: string) {
    if (busy.current) return;
    busy.current = true;
    setState({ ...EMPTY_MCP, command, pending: true });
    const started = performance.now();
    const fail = (error: string) => setState((s) => ({ ...s, error }));
    try {
      const list = await rpc(1, "tools/list");
      if (!list.response.ok) return fail(httpError(list.response.status));
      const tools = ((list.json as { result?: { tools?: { name: string; description?: string }[] } })?.result?.tools ?? []);
      push({
        dir: "←",
        title: `${list.response.status} · ${list.ms} ms · ${tools.length} tool${tools.length === 1 ? "" : "s"}: ${tools.map((t) => t.name).join(", ")}`,
        body: tools.map((t) => `${t.name}: ${t.description ?? ""}`).join("\n"),
      });

      const call = await rpc(2, "tools/call", { name: "check_install", arguments: { command } });
      if (!call.response.ok) return fail(httpError(call.response.status));
      const result = (call.json as { result?: { isError?: boolean; content?: { text?: string }[] } })?.result;
      const text = result?.content?.[0]?.text ?? "";
      let verdict: GateVerdict | null = null;
      try {
        verdict = result?.isError ? null : parseVerdict(JSON.parse(text));
      } catch {
        verdict = null;
      }
      push({
        dir: "←",
        title: `${call.response.status} · ${call.ms} ms · ${verdict ? `GateVerdict ${verdict.final_verdict}` : "tool error"}`,
        body: verdict ? `content[0].text: GateVerdict JSON (${text.length.toLocaleString()} chars)` : text,
        bad: !verdict,
      });
      if (!verdict) return fail("The tool did not return a verdict this screen recognises. Treat it as a review.");
      setState((s) => ({ ...s, verdict, raw: call.json }));
    } catch {
      fail("The MCP endpoint is not reachable. Is the check API running on port 8000?");
    } finally {
      busy.current = false;
      setState((s) => ({ ...s, pending: false, elapsedMs: performance.now() - started }));
    }
  }

  return { state, run };
}
