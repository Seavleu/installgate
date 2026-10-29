"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import type { GateVerdict } from "@contracts";

export const C = { ok: "#3FD18B", warn: "#F2B84B", bad: "#FF7B72", skip: "#7D8799", dim: "#8B95A7", muted: "#9AA4B5", link: "#6CB6FF" };
export const VERDICT = { ALLOW: [C.ok, "✔"], REVIEW: [C.warn, "▲"], BLOCK: [C.bad, "✖"] } as const;
const GLYPH = { ok: "✔", warn: "▲", bad: "✖", skip: "–" } as const;
export type Tone = keyof typeof GLYPH;

export const words = (value: string) => value.replaceAll("_", " ");

export function money(value: number): string {
  if (value === 0) return "$0";
  if (value < 0.01) return `$${value.toFixed(5)}`;
  return `$${value.toFixed(2)}`;
}

export function stripNulls(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(stripNulls);
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .filter(([, item]) => item !== null)
        .map(([key, item]) => [key, stripNulls(item)]),
    );
  }
  return value;
}

export function Segmented<T extends string>({
  id,
  label,
  options,
  value,
  onPick,
  danger,
}: {
  id: string;
  label: string;
  options: readonly (readonly [T, string])[];
  value: T | null;
  onPick: (value: T) => void;
  danger?: T;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <span id={id} className="text-xs font-semibold uppercase tracking-[0.06em] text-[#4B5563]">
        {label}
      </span>
      <div role="group" aria-labelledby={id} className="flex flex-wrap gap-1 rounded-[10px] bg-[#DDE1E7] p-1">
        {options.map(([key, text]) => {
          const on = key === value;
          return (
            <button
              key={key}
              type="button"
              aria-pressed={on}
              onClick={() => onPick(key)}
              className="min-h-11 cursor-pointer rounded-[7px] border-0 px-3.5 text-sm font-medium"
              style={{
                background: on ? (key === danger ? "#B42318" : "#14171C") : "transparent",
                color: on ? "#FFFFFF" : "#1F2933",
              }}
            >
              {text}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export function TerminalFrame({
  title,
  actions,
  footer,
  scrollKey,
  children,
}: {
  title: string;
  actions?: ReactNode;
  footer?: ReactNode;
  scrollKey?: string | number;
  children: ReactNode;
}) {
  const scroller = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [scrollKey]);
  return (
    <section
      aria-label="Terminal output"
      className="flex min-h-[32rem] flex-1 flex-col overflow-hidden rounded-xl border border-[#1F2633] bg-[#0B0E14]"
    >
      <div className="flex h-10 shrink-0 items-center gap-2 border-b border-[#1F2633] bg-[#121722] px-3">
        <svg aria-hidden="true" width="52" height="12" viewBox="0 0 52 12">
          <circle cx="6" cy="6" r="5" fill="#3A4252" />
          <circle cx="26" cy="6" r="5" fill="#3A4252" />
          <circle cx="46" cy="6" r="5" fill="#3A4252" />
        </svg>
        <span className="min-w-0 flex-1 truncate font-mono text-xs text-[#8B95A7]">{title}</span>
        {actions}
      </div>
      <div
        ref={scroller}
        aria-live="polite"
        className="min-h-0 flex-1 overflow-auto px-5 pb-4 pt-4 font-mono text-[13.5px] leading-[1.65] text-[#D6DEEB]"
      >
        {children}
      </div>
      {footer ? (
        <div className="shrink-0 border-t border-[#1F2633] bg-[#0E1219] px-5 py-3 font-mono text-[13.5px] leading-[1.65] text-[#D6DEEB]">
          {footer}
        </div>
      ) : null}
    </section>
  );
}

export function Prompt({ who = "~/agent-workspace", children }: { who?: string; children?: ReactNode }) {
  return (
    <div className="flex whitespace-pre-wrap">
      {who ? (
        <>
          <span style={{ color: C.ok }}>{who}</span>
          <span style={{ color: C.dim }}> $ </span>
        </>
      ) : null}
      {children}
    </div>
  );
}

export function Checking({ command }: { command: string }) {
  return (
    <div>
      <span style={{ color: C.dim }}>Checking </span>
      <span className="font-bold">{command}</span>
    </div>
  );
}

export function Cursor() {
  return <span aria-hidden="true" className="inline-block h-[1.1em] w-2 animate-pulse bg-[#D6DEEB] align-text-bottom" />;
}

export function Heading({ children }: { children: ReactNode }) {
  return <div className="mt-[18px] font-bold">{children}</div>;
}

export function StepRow({ tone, name, detail, ms }: { tone: Tone; name: string; detail: string; ms?: string }) {
  const clock = (ms ?? "–").replace(/ ms\b/, "ms").replace(/ s\b/, "s");
  return (
    <div className="grid grid-cols-[1.25rem_22ch_minmax(0,1fr)_4.5rem] gap-x-2">
      <span className="font-bold" style={{ color: C[tone] }}>
        {GLYPH[tone]}
      </span>
      <span className="font-bold">{name}</span>
      <span className="break-words" style={{ color: C.dim }}>
        {detail}
      </span>
      <span className="text-right" style={{ color: C.skip }}>
        {clock}
      </span>
    </div>
  );
}

export function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!copied) return;
    const id = window.setTimeout(() => setCopied(false), 1600);
    return () => window.clearTimeout(id);
  }, [copied]);
  return (
    <button
      type="button"
      onClick={() => {
        void navigator.clipboard?.writeText(text).catch(() => undefined);
        setCopied(true);
      }}
      className="min-h-8 shrink-0 cursor-pointer rounded-md border border-[#2F3747] bg-[#151B26] px-2.5 font-sans text-[12px] font-medium text-[#D6DEEB] transition-transform active:scale-[0.98]"
    >
      {copied ? "Copied" : label}
    </button>
  );
}

export function Diff({ from, to }: { from: string; to: string }) {
  return (
    <div className="pl-4">
      <div className="whitespace-pre-wrap break-all" style={{ color: C.bad }}>
        - {from}
      </div>
      <div className="whitespace-pre-wrap break-all" style={{ color: C.ok }}>
        + {to}
      </div>
    </div>
  );
}

const RULE: Record<string, string> = {
  not_found: "P1",
  osv_malicious: "P2",
  runtime_below_floor: "P3",
  typosquat_new_project: "P4",
  typosquat: "P5",
  new_project: "P6",
  new_release: "P6",
  hf_pickle: "P7",
  maintainer_change: "P8",
  check_unavailable: "P10",
};
const KIND = { ALLOW: "success", REVIEW: "warning", BLOCK: "error" } as const;
const SKIP_OBS = new Set(["first_upload", "latest_upload"]);

function clip(text: string, n: number): string {
  const compact = text.replace(/\s+/g, " ");
  return compact.length <= n ? compact : `${compact.slice(0, n - 1)}…`;
}

function observedLine(observed: Record<string, unknown>): string {
  const parts: string[] = [];
  for (const [key, item] of Object.entries(observed)) {
    if (SKIP_OBS.has(key)) continue;
    let raw = typeof item === "string" ? item : JSON.stringify(item);
    if (key === "title" || key === "snippet" || key === "sha256" || key === "artifact_sha256") raw = clip(raw, 56);
    parts.push(`${key}: ${raw}`);
    if (parts.length === 4) break;
  }
  return parts.join(" · ");
}

function ruleId(v: GateVerdict): string {
  const want = v.final_verdict === "BLOCK" ? "hard" : "soft";
  const hit = v.evidence.find((e) => e.severity === want) ?? v.evidence[0];
  return hit ? (RULE[hit.kind] ?? "") : "";
}

function cited(text: string, ids: string[]): string {
  return ids.every((id) => text.includes(id)) ? text : `${text} [${ids.join(", ")}]`;
}

function substituteLine(command: string, verdict: GateVerdict): string | null {
  const remediation = verdict.remediation;
  if (remediation?.status !== "VERIFIED_SUBSTITUTE" || !remediation.approved_requirement) return null;
  const name = remediation.original.name;
  if (command.includes(name)) return command.replace(name, remediation.approved_requirement);
  return remediation.approved_requirement;
}

function pinnedCommand(verdict: GateVerdict): string | null {
  const { ecosystem, name, version, artifact_sha256 } = verdict.target;
  if (!version) return null;
  if (ecosystem === "npm") return `npm install ${name}@${version}`;
  if (ecosystem === "pypi") {
    return `pip install ${name}==${version}${artifact_sha256 ? ` --hash=sha256:${artifact_sha256}` : ""}`;
  }
  return null;
}

function clipHash(cmd: string): string {
  return cmd.replace(/--hash=sha256:([0-9a-f]{12})[0-9a-f]+/gi, "--hash=sha256:$1…");
}

/** Same command the CLI would run after [Y/n]. Copy is pip-portable; display matches `ig`. */
export function proposedRun(verdict: GateVerdict): { copy: string; display: string; defaultYes: boolean } | null {
  const rem = verdict.remediation;
  if (rem?.status === "VERIFIED_SUBSTITUTE" && rem.approved_requirement) {
    const req = rem.approved_requirement;
    const hashed = req.includes("--hash=");
    const copy = hashed ? `pip install ${req} --no-deps` : req.startsWith("pip ") ? req : `pip install ${req}`;
    const display = hashed ? `uv pip install --no-deps ${clipHash(req)}` : clipHash(copy);
    return { copy, display, defaultYes: false };
  }
  const { ecosystem, name, version, artifact_sha256 } = verdict.target;
  if (verdict.final_verdict !== "ALLOW" || !version) return null;
  if (ecosystem === "npm") {
    const copy = `npm install ${name}@${version}`;
    return { copy, display: copy, defaultYes: true };
  }
  if (ecosystem === "pypi") {
    const req = `${name}==${version}${artifact_sha256 ? ` --hash=sha256:${artifact_sha256}` : ""}`;
    const copy = artifact_sha256 ? `pip install ${req} --no-deps` : `pip install ${name}==${version}`;
    const display = artifact_sha256
      ? `uv pip install --no-deps ${clipHash(req)}`
      : `pip install ${name}==${version}`;
    return { copy, display, defaultYes: true };
  }
  return null;
}

export type ConfirmState = "wait" | "yes" | "no";

export function ConfirmLine({
  display,
  defaultYes,
  state,
  onAnswer,
}: {
  display: string;
  defaultYes: boolean;
  state: ConfirmState;
  onAnswer?: (yes: boolean) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (state === "wait") input.current?.focus();
  }, [state, display]);

  if (state === "yes") {
    return <div style={{ color: C.ok }}>{"  "}copied. paste in your shell</div>;
  }
  if (state === "no") {
    return <div style={{ color: C.dim }}>{"  "}skipped</div>;
  }

  const hint = defaultYes ? "Y/n" : "y/N";
  return (
    <div className="flex flex-wrap items-baseline gap-2">
      <span style={{ color: C.dim }}>
        {"  "}? Run `{display}` [{hint}]
      </span>
      {onAnswer ? (
        <input
          ref={input}
          aria-label="Confirm install. Y copies the pinned command. N skips."
          className="w-16 border-0 bg-transparent p-0 font-mono text-[#D6DEEB] caret-[#D6DEEB] outline-none"
          spellCheck={false}
          autoComplete="off"
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              onAnswer(defaultYes);
              return;
            }
            if (event.key === "y" || event.key === "Y") {
              event.preventDefault();
              onAnswer(true);
              return;
            }
            if (event.key === "n" || event.key === "N") {
              event.preventDefault();
              onAnswer(false);
            }
          }}
        />
      ) : null}
    </div>
  );
}

function receiptLine(v: GateVerdict, elapsedMs: number): string {
  const took = `${(elapsedMs / 1000).toFixed(2)}s`;
  const r = v.receipt;
  if (!r || r.calls.length === 0) return `no model · $0 · ${took}`;
  const chain = r.calls
    .map((c) => `${c.tier[0].toUpperCase()}${c.tier.slice(1)} ${c.prompt_tokens + c.completion_tokens} tok`)
    .join(" → ");
  const tavily = r.tavily_calls ? ` · Tavily ${r.tavily_calls}` : "";
  return `${chain} · ${money(r.total_cost_usd)} (−${r.savings_pct.toFixed(0)}% vs all-Ultra)${tavily} · ${took}`;
}

export function Banner({
  verdict,
  name,
  code,
}: {
  verdict: keyof typeof KIND;
  name: string;
  code?: string;
}) {
  const kind = KIND[verdict];
  const tone = { ALLOW: C.ok, REVIEW: C.warn, BLOCK: C.bad }[verdict];
  const label = code ? `${kind}[${code}]` : kind;
  return (
    <div className="mt-4 font-bold" style={{ color: tone }}>
      {label}: {verdict} {name}
    </div>
  );
}

function EvidenceSpan({
  id,
  severity,
  source,
  kind,
  web,
  facts,
}: {
  id: string;
  severity: string;
  source: string;
  kind: string;
  web: boolean;
  facts: string;
}) {
  const tone = severity === "hard" ? C.bad : severity === "soft" ? C.warn : C.skip;
  return (
    <div className="whitespace-pre-wrap">
      <div>
        <span style={{ color: tone }}>×</span> {words(kind)}
      </div>
      <div style={{ color: C.dim }}>
        {"   ╭─[ "}
        <span style={{ color: C.link }}>
          {id} {severity}
          {web ? " · web" : ""} · {source}
        </span>
        {" ]"}
      </div>
      {facts ? <div style={{ color: C.dim }}>{`   │  ${facts}`}</div> : null}
      <div style={{ color: C.dim }}>{"   ╰──"}</div>
    </div>
  );
}

/** Same layout as `ig` in a TTY: uv/ruff/cargo diagnostics. */
export function VerdictView({
  verdict: v,
  command,
  spendCapped,
  elapsedMs,
  confirm,
  onConfirm,
}: {
  verdict: GateVerdict;
  command: string;
  spendCapped: boolean;
  elapsedMs: number;
  confirm?: ConfirmState;
  onConfirm?: (yes: boolean) => void;
}) {
  const safe = substituteLine(command, v);
  const allow = v.final_verdict === "ALLOW" ? pinnedCommand(v) : null;
  const pin = v.target.version ? `${v.target.name}==${v.target.version}` : v.target.name;
  const run = proposedRun(v);

  return (
    <>
      <Banner verdict={v.final_verdict} name={pin} code={ruleId(v)} />
      <div style={{ color: C.dim }}>
        {"  "}
        {v.target.ecosystem} · risk {v.risk_score.toFixed(2)} · {words(v.outcome).toLowerCase()}
      </div>
      {v.failed_closed && <div style={{ color: C.warn }}>warning: a lookup failed, so this stays a review</div>}
      {spendCapped && <div style={{ color: C.warn }}>warning: the daily model budget is spent</div>}

      {v.evidence.length === 0 ? (
        <div style={{ color: C.dim }}>{"  "}no findings · model skipped</div>
      ) : (
        v.evidence.map((e) => (
          <EvidenceSpan
            key={e.id}
            id={e.id}
            severity={e.severity}
            source={e.source}
            kind={e.kind}
            web={e.trust === "retrieved_untrusted"}
            facts={observedLine(e.observed)}
          />
        ))
      )}

      {v.explanation.map((s) => (
        <div key={s.text} style={{ color: C.skip }}>
          {"  "}note: {cited(s.text, s.evidence_ids)}
        </div>
      ))}
      {v.dropped_sentences > 0 && (
        <div style={{ color: C.skip }}>
          {"  "}note: {v.dropped_sentences} sentence(s) dropped (no evidence id)
        </div>
      )}

      {safe && v.remediation && (
        <>
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div style={{ color: C.ok }}>
              {"  "}help: use substitute ({words(v.remediation.candidate_source ?? "closed set")} · re-checked{" "}
              {v.remediation.recheck_evidence_ids.join(", ")})
            </div>
            <CopyButton key={safe} text={run?.copy ?? safe} label="Copy" />
          </div>
          <Diff from={command} to={safe} />
          {v.remediation.equivalence_note ? (
            <div style={{ color: C.dim }}>
              {"  "}note: {v.remediation.equivalence_note}
            </div>
          ) : null}
        </>
      )}

      {!safe && v.final_verdict !== "ALLOW" && (
        <>
          <div style={{ color: C.warn }}>{"  "}help: no safe substitute in the closed candidate set</div>
          <div style={{ color: C.dim }}>{"  "}note: ask a human which package was meant, then check that name</div>
        </>
      )}

      {allow && (
        <>
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div className="min-w-0 break-all" style={{ color: C.ok }}>
              {"  "}help: {allow}
            </div>
            <CopyButton key={allow} text={run?.copy ?? allow} label="Copy" />
          </div>
          <div style={{ color: C.dim }}>{"  "}note: pinned artefact. Confirm to copy. The browser never installs.</div>
        </>
      )}

      <div style={{ color: C.dim }}>
        {"  "}note: {receiptLine(v, elapsedMs)}
      </div>
      {run && (
        <ConfirmLine
          display={run.display}
          defaultYes={run.defaultYes}
          state={confirm ?? "wait"}
          onAnswer={
            onConfirm
              ? (yes) => {
                  if (yes) void navigator.clipboard?.writeText(run.copy).catch(() => undefined);
                  onConfirm(yes);
                }
              : undefined
          }
        />
      )}
    </>
  );
}
