"use client";

import { useState, type ReactNode } from "react";
import type { GateVerdict } from "@contracts";

export const C = { ok: "#3FD18B", warn: "#F2B84B", bad: "#FF7B72", skip: "#7D8799", dim: "#8B95A7", muted: "#9AA4B5", link: "#6CB6FF" };
export const VERDICT = { ALLOW: [C.ok, "✔"], REVIEW: [C.warn, "▲"], BLOCK: [C.bad, "✖"] } as const;
const GLYPH = { ok: "✔", warn: "▲", bad: "✖", skip: "–" } as const;
export type Tone = keyof typeof GLYPH;

export const words = (value: string) => value.replaceAll("_", " ");
const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

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

export function TerminalFrame({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section
      aria-label="Terminal output"
      className="flex min-h-[640px] flex-1 flex-col overflow-hidden rounded-xl border border-[#1F2633] bg-[#0B0E14]"
    >
      <div className="flex h-[38px] items-center gap-2 border-b border-[#1F2633] bg-[#121722] px-4">
        <svg aria-hidden="true" width="52" height="12" viewBox="0 0 52 12">
          <circle cx="6" cy="6" r="5" fill="#3A4252" />
          <circle cx="26" cy="6" r="5" fill="#3A4252" />
          <circle cx="46" cy="6" r="5" fill="#3A4252" />
        </svg>
        <span className="flex-1 text-center font-mono text-xs text-[#8B95A7]">{title}</span>
        <span className="w-[52px]" />
      </div>
      <div
        aria-live="polite"
        className="min-h-0 flex-1 overflow-auto px-6 pb-6 pt-[18px] font-mono text-[13.5px] leading-[1.65] text-[#D6DEEB]"
      >
        {children}
      </div>
    </section>
  );
}

export function Prompt({ who = "~/agent-workspace", children }: { who?: string; children?: ReactNode }) {
  return (
    <div className="flex whitespace-pre-wrap">
      <span style={{ color: C.ok }}>{who}</span>
      <span style={{ color: C.dim }}> $ </span>
      {children}
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
  return (
    <div className="grid grid-cols-[22px_250px_minmax(0,1fr)_72px] gap-x-2">
      <span className="font-bold" style={{ color: C[tone] }}>
        {GLYPH[tone]}
      </span>
      <span>{name}</span>
      <span className="break-words" style={{ color: C.muted }}>
        {detail}
      </span>
      <span className="text-right" style={{ color: C.skip }}>
        {ms ?? "–"}
      </span>
    </div>
  );
}

export function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={() => {
        void navigator.clipboard?.writeText(text).catch(() => undefined);
        setCopied(true);
      }}
      className="min-h-11 shrink-0 cursor-pointer rounded-md border border-[#2F3747] bg-[#151B26] px-3.5 font-sans text-[13px] font-medium text-[#D6DEEB]"
    >
      {copied ? "Copied" : label}
    </button>
  );
}

export function Diff({ from, to }: { from: string; to: string }) {
  return (
    <div className="mt-1.5 overflow-hidden rounded-md border border-[#1F2633]">
      <div className="whitespace-pre-wrap break-all bg-[#2A1416] px-3 py-0.5 text-[#FF9B94]">- {from}</div>
      <div className="whitespace-pre-wrap break-all bg-[#10261C] px-3 py-0.5 text-[#7EE2AE]">+ {to}</div>
    </div>
  );
}

function observedLine(observed: Record<string, unknown>): string {
  return Object.entries(observed)
    .slice(0, 4)
    .map(([key, item]) => `${key}: ${typeof item === "string" ? item : JSON.stringify(item)}`)
    .join(" · ");
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
  if (ecosystem === "pypi") return `pip install "${name}==${version}"${artifact_sha256 ? ` --hash=sha256:${artifact_sha256}` : ""}`;
  return null;
}

function receiptLine(v: GateVerdict): string {
  const r = v.receipt;
  if (!r || r.calls.length === 0) return "No model calls · $0 · deterministic path only";
  const chain = r.calls
    .map((c) => `${c.tier[0].toUpperCase()}${c.tier.slice(1)} ${(c.prompt_tokens + c.completion_tokens).toLocaleString()} tok`)
    .join(" → ");
  const tavily = r.tavily_calls ? ` · Tavily ${plural(r.tavily_calls, "call")}` : "";
  return `Nemotron on Nebius Token Factory · ${chain} · ${money(r.total_cost_usd)} (all-Ultra ${money(r.counterfactual_all_ultra_usd)}, −${r.savings_pct.toFixed(0)}%)${tavily}`;
}

/** Everything after the pipeline steps: verdict, evidence, why, fix, receipt. */
export function VerdictView({
  verdict: v,
  command,
  spendCapped,
  elapsedMs,
}: {
  verdict: GateVerdict;
  command: string;
  spendCapped: boolean;
  elapsedMs: number;
}) {
  const safe = substituteLine(command, v);
  const allow = v.final_verdict === "ALLOW" ? pinnedCommand(v) : null;
  const [vColor, vGlyph] = VERDICT[v.final_verdict];
  const grid4 = "grid grid-cols-[56px_92px_120px_minmax(0,1fr)] gap-x-3";

  return (
    <>
      <div className="mt-[18px] flex flex-wrap items-center gap-3">
        <span className="rounded px-2.5 py-px font-bold text-[#0B0E14]" style={{ background: vColor }}>
          {vGlyph} {v.final_verdict}
        </span>
        <span className="font-bold">{v.target.name}</span>
        <span style={{ color: C.muted }}>
          {v.target.ecosystem} · risk {v.risk_score.toFixed(2)} · {words(v.outcome).toLowerCase()}
        </span>
      </div>
      {v.failed_closed && <div style={{ color: C.warn }}>A lookup failed, so this stays a review.</div>}
      {spendCapped && <div style={{ color: C.warn }}>The daily model budget is spent. This verdict is from the decision engine.</div>}

      <Heading>Evidence</Heading>
      {v.evidence.length === 0 ? (
        <div style={{ color: C.muted }}>No findings. Nothing to explain, so no model was called.</div>
      ) : (
        <>
          <div className={grid4} style={{ color: C.skip }}>
            <span>ID</span>
            <span>SEVERITY</span>
            <span>SOURCE</span>
            <span>FINDING</span>
          </div>
          {v.evidence.map((e) => (
            <div key={e.id} className={grid4}>
              <span style={{ color: C.link }}>{e.id}</span>
              <span style={{ color: e.severity === "hard" ? C.bad : e.severity === "soft" ? C.warn : C.dim }}>
                {e.severity}
                {e.trust === "retrieved_untrusted" ? " · web" : ""}
              </span>
              <span style={{ color: C.muted }}>{words(e.source)}</span>
              <span className="break-words">
                {words(e.kind)}
                {Object.keys(e.observed).length > 0 && <span style={{ color: C.muted }}> · {observedLine(e.observed)}</span>}
              </span>
            </div>
          ))}
        </>
      )}

      {(v.explanation.length > 0 || v.dropped_sentences > 0) && (
        <>
          <Heading>Why</Heading>
          {v.explanation.map((s) => (
            <div key={s.text}>
              <span style={{ color: C.skip }}>• </span>
              {s.text} <span style={{ color: C.link }}>[{s.evidence_ids.join(", ")}]</span>
            </div>
          ))}
          <div style={{ color: C.skip }}>
            Validator: {v.explanation.length} of {v.explanation.length + v.dropped_sentences} sentences cited ·{" "}
            {v.dropped_sentences} dropped{v.dropped_sentences > 0 ? " (no evidence id)" : ""}
          </div>
        </>
      )}

      {safe && v.remediation && (
        <>
          <div className="mt-[18px] flex items-center justify-between gap-4">
            <span className="font-bold">
              Suggested fix{" "}
              <span className="font-normal" style={{ color: C.skip }}>
                ({words(v.remediation.candidate_source ?? "closed set")} · re-checked [{v.remediation.recheck_evidence_ids.join(", ")}])
              </span>
            </span>
            <CopyButton key={safe} text={safe} label="Copy fix" />
          </div>
          <Diff from={command} to={safe} />
          <div className="mt-1.5" style={{ color: C.muted }}>
            Not run. Confirm it, then run it yourself or let your agent run it. {v.remediation.equivalence_note}.
          </div>
        </>
      )}

      {!safe && v.final_verdict !== "ALLOW" && (
        <>
          <Heading>Suggested fix</Heading>
          <div style={{ color: C.warn }}>▲ No safe substitute. The closed candidate set has no match, so InstallGate will not guess a name.</div>
          <div style={{ color: C.muted }}>Ask a human which package was meant, then check that name.</div>
        </>
      )}

      {allow && (
        <>
          <Heading>Proceed</Heading>
          <div className="whitespace-pre-wrap break-all rounded-md border border-[#1F2633] px-3 py-0.5 text-[#7EE2AE]">{allow}</div>
          <div className="mt-1.5" style={{ color: C.muted }}>
            Pinned to the exact artifact that was checked. InstallGate does not run it.
          </div>
        </>
      )}

      <div className="mt-[18px] border-t border-[#1F2633] pt-2.5" style={{ color: C.dim }}>
        {receiptLine(v)}
      </div>
      <div style={{ color: vColor }}>
        {v.final_verdict} · next: {words(v.next_action)} · {(elapsedMs / 1000).toFixed(2)} s
      </div>
    </>
  );
}
