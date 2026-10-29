"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  C,
  Checking,
  CopyButton,
  Cursor,
  Prompt,
  StepRow,
  TerminalFrame,
  VerdictView,
  type ConfirmState,
} from "./terminal";
import { useMcpCheck, useStreamCheck, type StreamState } from "./use-checks";

const SCENARIOS = [
  { label: "typosquat", command: "pip install reqeusts" },
  { label: "missing", command: "pip install no-such-pkg-xyz" },
  { label: "clean", command: "pip install requests" },
  { label: "numpy", command: "pip install numpy" },
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

const HOOK = 'eval "$(ig hook)"';

function TitleToggle<T extends string>({
  options,
  value,
  onPick,
  danger,
}: {
  options: readonly (readonly [T, string])[];
  value: T;
  onPick: (value: T) => void;
  danger?: T;
}) {
  return (
    <div role="group" className="flex gap-0.5 rounded-md bg-[#0B0E14] p-0.5">
      {options.map(([key, text]) => {
        const on = key === value;
        return (
          <button
            key={key}
            type="button"
            aria-pressed={on}
            onClick={() => onPick(key)}
            className="h-7 cursor-pointer rounded px-2 font-sans text-[11px] font-medium"
            style={{
              background: on ? (key === danger ? "#B42318" : "#1E2633") : "transparent",
              color: on ? "#FFFFFF" : "#8B95A7",
            }}
          >
            {text}
          </button>
        );
      })}
    </div>
  );
}

export function Demo() {
  const [view, setView] = useState<"terminal" | "mcp">("terminal");
  const [command, setCommand] = useState("");
  const [gate, setGate] = useState<"on" | "off">("on");
  const [out, setOut] = useState<"pretty" | "json">("pretty");
  const [origin, setOrigin] = useState("http://localhost:3000");
  const [api, setApi] = useState<"live" | "down" | "…">("…");
  const [confirm, setConfirm] = useState<ConfirmState>("wait");
  const [log, setLog] = useState<StreamState[]>([]);
  const [last, setLast] = useState("");
  const prompt = useRef<HTMLInputElement>(null);
  const capture = useRef(false);
  const stream = useStreamCheck();
  const agent = useMcpCheck();

  useEffect(() => setOrigin(window.location.origin), []);
  useEffect(() => {
    prompt.current?.focus();
  }, [view]);
  useEffect(() => {
    let stop = false;
    fetch("/api/health")
      .then((r) => (stop ? undefined : setApi(r.ok ? "live" : "down")))
      .catch(() => {
        if (!stop) setApi("down");
      });
    return () => {
      stop = true;
    };
  }, []);
  useEffect(() => {
    setConfirm("wait");
  }, [
    stream.state.command,
    stream.state.verdict,
    stream.state.pending,
    agent.state.command,
    agent.state.verdict,
  ]);
  useEffect(() => {
    const s = stream.state;
    if (!capture.current || s.pending || !s.command || !s.verdict) return;
    capture.current = false;
    setLog((prev) => [{ ...s }, ...prev].slice(0, 12));
  }, [stream.state]);

  function submit(next: string) {
    const trimmed = next.trim();
    if (!trimmed) return;
    setLast(trimmed);
    setCommand(trimmed);
    setConfirm("wait");
    capture.current = view === "terminal" && gate === "on";
    if (view === "mcp") void agent.run(trimmed);
    else if (gate === "on") void stream.run(trimmed);
    else stream.skip(trimmed);
  }

  function answered(yes: boolean) {
    setConfirm(yes ? "yes" : "no");
    requestAnimationFrame(() => prompt.current?.focus());
  }

  const pending = view === "mcp" ? agent.state.pending : stream.state.pending;
  const mcpConfig = JSON.stringify(
    { mcpServers: { installgate: { url: `${origin}/api/mcp` } } },
    null,
    2,
  );
  const s = stream.state;
  const a = agent.state;
  const pin =
    s.verdict?.target.version != null
      ? `${s.verdict.target.name}==${s.verdict.target.version}`
      : s.verdict?.target.name;

  const input = (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        submit(command);
      }}
    >
      <Prompt who={view === "mcp" ? "agent" : ""}>
        <span>{view === "mcp" ? "check_install " : "ig "}</span>
        <label className="sr-only" htmlFor="command">
          Install command
        </label>
        <input
          ref={prompt}
          id="command"
          value={command}
          onChange={(event) => setCommand(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "ArrowUp" && last && !command) {
              event.preventDefault();
              setCommand(last);
            }
          }}
          spellCheck={false}
          autoComplete="off"
          placeholder="pip install numpy"
          className="min-w-0 flex-1 border-0 bg-transparent p-0 font-mono text-[#D6DEEB] caret-[#D6DEEB] outline-none placeholder:text-[#3A4252]"
        />
        <span style={{ color: C.skip }}>{pending ? "running…" : "↵"}</span>
      </Prompt>
    </form>
  );

  return (
    <main className="mx-auto flex min-h-[100dvh] max-w-[1400px] flex-col gap-3 px-4 py-4 md:px-6">
      <a
        href="#command"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-10 focus:bg-[#14171C] focus:px-3 focus:py-2 focus:text-white"
      >
        Skip to command
      </a>
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 items-baseline gap-3">
          <h1 className="m-0 text-[18px] font-semibold tracking-[-0.02em]">InstallGate</h1>
          <p className="m-0 truncate text-[13px] text-[#4B5563]">
            Paste an install. After ALLOW, y copies the pin. Nothing is installed here.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3 text-[12px] text-[#4B5563]">
          <span className="inline-flex items-center gap-1.5">
            <span
              aria-hidden="true"
              className="inline-block h-1.5 w-1.5 rounded-full"
              style={{ background: api === "live" ? C.ok : api === "down" ? C.bad : C.skip }}
            />
            api {api}
          </span>
          <code className="rounded bg-[#DDE1E7] px-1.5 py-0.5 font-mono text-[11px] text-[#14171C]">{HOOK}</code>
          <CopyButton text={HOOK} label="Copy hook" />
          <Link href="/mockup" className="text-[#14171C] underline">
            mockup
          </Link>
        </div>
      </header>

      <div className="flex min-h-0 flex-1 flex-col gap-3 lg:flex-row">
        {log.length > 0 && (
          <aside
            aria-label="Recent checks"
            className="flex shrink-0 gap-1 overflow-x-auto lg:w-52 lg:flex-col lg:overflow-y-auto"
          >
            {log.map((item, i) => {
              const v = item.verdict?.final_verdict ?? (item.gateOff ? "off" : "…");
              const tone = v === "ALLOW" ? C.ok : v === "BLOCK" ? C.bad : v === "REVIEW" ? C.warn : C.skip;
              const label = item.verdict
                ? `${item.verdict.target.name}${item.verdict.target.version ? `==${item.verdict.target.version}` : ""}`
                : item.command ?? "";
              const on =
                s.command === item.command && s.elapsedMs === item.elapsedMs && !s.pending;
              return (
                <button
                  key={`${item.command}-${item.elapsedMs}-${i}`}
                  type="button"
                  aria-current={on ? "true" : undefined}
                  onClick={() => {
                    capture.current = false;
                    setView("terminal");
                    setCommand(item.command ?? "");
                    stream.restore(item);
                    setConfirm("wait");
                  }}
                  className="flex min-w-[9.5rem] cursor-pointer items-center gap-2 rounded-md border px-2 py-1.5 text-left text-[12px] hover:bg-white"
                  style={{
                    borderColor: on ? "#14171C" : "transparent",
                    background: on ? "#FFFFFF" : "transparent",
                  }}
                >
                  <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: tone }} />
                  <span className="min-w-0 truncate font-mono">
                    <span className="font-medium">{v}</span> {label}
                  </span>
                </button>
              );
            })}
          </aside>
        )}

        {view === "terminal" ? (
          <TerminalFrame
            title={s.command ? `ig ${s.command}` : "ig · live from POST /check/stream"}
            scrollKey={`${s.events.length}-${s.pending}-${confirm}`}
            actions={
              <div className="flex items-center gap-1">
                <TitleToggle
                  options={[["terminal", "ig"], ["mcp", "MCP"]] as const}
                  value={view}
                  onPick={setView}
                />
                <TitleToggle
                  options={[["pretty", "TTY"], ["json", "JSON"]] as const}
                  value={out}
                  onPick={setOut}
                />
                <TitleToggle
                  options={[["on", "Gate"], ["off", "Off"]] as const}
                  value={gate}
                  onPick={setGate}
                  danger="off"
                />
              </div>
            }
            footer={input}
          >
            {!s.command && (
              <div className="flex flex-col gap-4">
                <div style={{ color: C.dim }}>
                  # Same output as the CLI. Enter checks. y copies the pinned command (the browser never
                  installs).
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {SCENARIOS.map((item) => (
                    <button
                      key={item.command}
                      type="button"
                      onClick={() => submit(item.command)}
                      className="cursor-pointer rounded-md border border-[#1F2633] bg-[#121722] px-2.5 py-1 font-mono text-[12px] text-[#D6DEEB] hover:border-[#3A4252]"
                    >
                      <span style={{ color: C.skip }}>{item.label} </span>
                      {item.command}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {s.command && (s.gateOff ? <Prompt who="">{s.command}</Prompt> : <Checking command={s.command} />)}
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
                  <StepRow
                    key={i}
                    tone={e.status}
                    name={STAGE_NAME[e.stage] ?? e.stage}
                    detail={e.detail}
                    ms={`${e.ms}ms`}
                  />
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
              <VerdictView
                verdict={s.verdict}
                command={s.command}
                spendCapped={s.spendCapped}
                elapsedMs={s.elapsedMs}
                confirm={confirm}
                onConfirm={answered}
              />
            )}
          </TerminalFrame>
        ) : (
          <TerminalFrame
            title={`check_install · ${origin}/api/mcp`}
            scrollKey={`${a.frames.length}-${a.pending}`}
            actions={
              <div className="flex items-center gap-1">
                <TitleToggle
                  options={[["terminal", "ig"], ["mcp", "MCP"]] as const}
                  value={view}
                  onPick={setView}
                />
                <TitleToggle
                  options={[["pretty", "TTY"], ["json", "JSON"]] as const}
                  value={out}
                  onPick={setOut}
                />
              </div>
            }
            footer={input}
          >
            {!a.command && (
              <div style={{ color: C.dim }}>
                # What a coding agent does before it installs: call check_install over MCP.
                <br /># Type an install command, or pick a scenario from the empty ig view.
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
                  Agent decision:{" "}
                  <span style={{ color: C.warn }}>{a.verdict.next_action.replaceAll("_", " ")}</span>
                </div>
                <div style={{ color: C.muted }}>{AGENT_DOES[a.verdict.next_action]}</div>
                {out === "json" ? (
                  <pre className="m-0 mt-2 whitespace-pre-wrap break-all font-[inherit]">
                    {JSON.stringify(a.raw, null, 2)}
                  </pre>
                ) : (
                  <VerdictView
                    verdict={a.verdict}
                    command={a.command}
                    spendCapped={false}
                    elapsedMs={a.elapsedMs}
                    confirm={confirm}
                    onConfirm={answered}
                  />
                )}
              </>
            )}
          </TerminalFrame>
        )}
      </div>

      <details className="rounded-xl bg-[#DDE1E7] px-4 py-3">
        <summary className="cursor-pointer text-[13px] font-semibold">
          MCP for Cursor or Claude
          <span className="ml-2 font-normal text-[#4B5563]">
            same GateVerdict as <code>ig</code>
            {pin ? ` · last pin ${pin}` : ""}
          </span>
        </summary>
        <div className="mt-3 flex flex-wrap items-start justify-between gap-3">
          <CopyButton text={mcpConfig} label="Copy MCP config" />
          <pre className="m-0 w-full overflow-x-auto rounded-md bg-[#0B0E14] p-3 font-mono text-[11px] text-[#D6DEEB]">
            {mcpConfig}
          </pre>
        </div>
      </details>
    </main>
  );
}
