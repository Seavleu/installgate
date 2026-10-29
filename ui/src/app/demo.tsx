"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { C, CopyButton, Cursor, Prompt, Segmented, StepRow, TerminalFrame, VerdictView } from "./terminal";
import { useMcpCheck, useStreamCheck } from "./use-checks";

const SCENARIOS = [
  { label: "Typosquat", command: "pip install reqeusts" },
  { label: "Hallucinated name", command: "pip install no-such-pkg-xyz" },
  { label: "Clean package", command: "pip install requests" },
  { label: "npm", command: "npm install left-pad" },
];

const STAGE_NAME: Record<string, string> = {
  parse: "Parse target",
  registry: "Registry metadata",
  osv: "OSV.dev",
  checks: "Deterministic checks",
  tavily: "Tavily (untrusted)",
  policy: "Policy",
  model: "Nemotron · Token Factory",
  validate: "Validator",
  substitute: "Substitute",
  pin: "Pin",
};

const AGENT_DOES = {
  proceed: "Agent may run the pinned command. InstallGate never runs it.",
  use_substitute: "Agent shows you the diff and waits for your confirmation.",
  ask_human: "Agent stops and asks you which package you meant.",
  abort: "Agent stops.",
} as const;

export function Demo() {
  const [view, setView] = useState<"terminal" | "mcp">("terminal");
  const [command, setCommand] = useState(SCENARIOS[0].command);
  const [gate, setGate] = useState<"on" | "off">("on");
  const [out, setOut] = useState<"pretty" | "json">("pretty");
  const [origin, setOrigin] = useState("http://localhost:3000");
  const stream = useStreamCheck();
  const agent = useMcpCheck();

  useEffect(() => setOrigin(window.location.origin), []);

  function submit(next: string) {
    const trimmed = next.trim();
    if (!trimmed) return;
    if (view === "mcp") void agent.run(trimmed);
    else if (gate === "on") void stream.run(trimmed);
    else stream.skip(trimmed);
  }

  const pending = view === "mcp" ? agent.state.pending : stream.state.pending;
  const scenario = SCENARIOS.find((s) => s.command === command.trim())?.command ?? null;
  const mcpConfig = JSON.stringify({ mcpServers: { installgate: { url: `${origin}/api/mcp` } } }, null, 2);

  const input = (
    <form
      className="mt-2.5"
      onSubmit={(event) => {
        event.preventDefault();
        submit(command);
      }}
    >
      <Prompt who={view === "mcp" ? "agent" : "~/agent-workspace"}>
        <span>{view === "mcp" ? "check_install " : gate === "on" ? "installgate check " : ""}</span>
        <label className="sr-only" htmlFor="command">
          Install command
        </label>
        <input
          id="command"
          value={command}
          onChange={(event) => setCommand(event.target.value)}
          spellCheck={false}
          autoComplete="off"
          className="min-w-0 flex-1 border-0 bg-transparent p-0 font-mono text-[#D6DEEB] caret-[#D6DEEB] outline-none"
        />
        <span style={{ color: C.skip }}>{pending ? "running…" : "↵ to run"}</span>
      </Prompt>
    </form>
  );

  const s = stream.state;
  const a = agent.state;

  return (
    <main className="mx-auto flex min-h-screen max-w-[1280px] flex-col gap-4 px-8 py-7">
      <header className="flex flex-wrap items-end justify-between gap-6">
        <div>
          <h1 className="m-0 text-[22px] font-semibold tracking-[-0.01em]">InstallGate</h1>
          <p className="mt-1 text-sm text-[#4B5563]">
            Pre-install trust gate for coding agents · live, nothing is installed ·{" "}
            <Link href="/mockup" className="text-[#14171C] underline">
              design mockup
            </Link>
          </p>
        </div>
        <p className="m-0 text-[13px] text-[#4B5563]">Metadata only · InstallGate never runs the command</p>
      </header>

      <div className="flex flex-wrap items-end gap-6">
        <Segmented
          id="lbl-view"
          label="Caller"
          options={[["terminal", "Terminal"], ["mcp", "Agent (MCP)"]] as const}
          value={view}
          onPick={setView}
        />
        <Segmented
          id="lbl-scenario"
          label="Scenario"
          options={SCENARIOS.map((x) => [x.command, x.label] as const)}
          value={scenario}
          onPick={(next) => {
            setCommand(next);
            submit(next);
          }}
        />
        {view === "terminal" && (
          <Segmented id="lbl-gate" label="Gate" options={[["on", "On"], ["off", "Off"]] as const} value={gate} onPick={setGate} danger="off" />
        )}
        <Segmented id="lbl-output" label="Output" options={[["pretty", "Pretty"], ["json", "JSON"]] as const} value={out} onPick={setOut} />
      </div>

      {view === "terminal" ? (
        <TerminalFrame title="agent-workspace — zsh · live from POST /check/stream">
          {!s.command && (
            <div style={{ color: C.dim }}># Pick a scenario, or type any pip or npm install command and press Enter. Each stage prints when it finishes.</div>
          )}
          {s.command && (
            <Prompt>
              <span>{s.gateOff ? s.command : `installgate check "${s.command}"`}</span>
            </Prompt>
          )}
          {s.gateOff && (
            <div className="mt-1" style={{ color: "#FF9B94" }}>
              # No check ran. The agent runs this as-is, with this shell&apos;s credentials in reach.
            </div>
          )}

          {out === "json" &&
            s.raw.map((line, i) => (
              <div key={i} className="whitespace-pre-wrap break-all">
                {line}
              </div>
            ))}

          {out === "pretty" && s.command && !s.gateOff && (
            <div className="mt-1">
              {s.events.map((e, i) => (
                <StepRow key={i} tone={e.status} name={STAGE_NAME[e.stage] ?? e.stage} detail={e.detail} ms={`${e.ms} ms`} />
              ))}
            </div>
          )}
          {s.pending && (
            <div style={{ color: C.dim }}>
              <Cursor /> reading metadata, the package is not installed
            </div>
          )}
          {s.error && <div style={{ color: C.bad }}>{s.error}</div>}
          {out === "pretty" && s.verdict && s.command && (
            <VerdictView verdict={s.verdict} command={s.command} spendCapped={s.spendCapped} elapsedMs={s.elapsedMs} />
          )}
          {input}
        </TerminalFrame>
      ) : (
        <TerminalFrame title={`coding agent — MCP Streamable HTTP · ${origin}/api/mcp`}>
          {!a.command && (
            <div style={{ color: C.dim }}>
              # This is what a coding agent does before it installs: call the real check_install tool over MCP.
              <br /># Pick a scenario, or type an install command and press Enter.
            </div>
          )}
          {a.frames.map((f, i) => (
            <div key={i} className={f.dir === "→" ? "mt-2" : ""}>
              <div style={{ color: f.dir === "→" ? C.link : f.bad ? C.bad : C.ok }}>
                {f.dir} {f.title}
              </div>
              {(f.dir === "→" || out === "json") && (
                <div className="whitespace-pre-wrap break-all" style={{ color: C.dim }}>
                  {f.body}
                </div>
              )}
            </div>
          ))}
          {a.pending && (
            <div style={{ color: C.dim }}>
              <Cursor /> waiting for the tool result
            </div>
          )}
          {a.error && <div style={{ color: C.bad }}>{a.error}</div>}
          {a.verdict && a.command && (
            <>
              <div className="mt-[18px] font-bold">
                Agent decision: <span style={{ color: C.warn }}>{a.verdict.next_action.replaceAll("_", " ")}</span>
              </div>
              <div style={{ color: C.muted }}>{AGENT_DOES[a.verdict.next_action]}</div>
              {out === "json" ? (
                <pre className="m-0 mt-2 whitespace-pre-wrap break-all font-[inherit]">{JSON.stringify(a.raw, null, 2)}</pre>
              ) : (
                <VerdictView verdict={a.verdict} command={a.command} spendCapped={false} elapsedMs={a.elapsedMs} />
              )}
            </>
          )}
          {input}
        </TerminalFrame>
      )}

      <section className="flex flex-wrap items-start justify-between gap-4 rounded-xl bg-[#DDE1E7] p-4">
        <div className="min-w-0 flex-1">
          <h2 className="m-0 text-sm font-semibold">Test it from your own agent</h2>
          <p className="mt-1 text-[13px] text-[#4B5563]">
            Add this MCP server to Cursor or Claude, then ask the agent to install <code>reqeusts</code>. It calls{" "}
            <code>check_install</code> first and gets the same verdict you see here.
          </p>
          <pre className="m-0 mt-2 overflow-x-auto rounded-md bg-[#0B0E14] p-3 font-mono text-xs text-[#D6DEEB]">{mcpConfig}</pre>
        </div>
        <div className="flex gap-2 pt-6">
          <CopyButton text={mcpConfig} label="Copy MCP config" />
        </div>
      </section>
    </main>
  );
}
