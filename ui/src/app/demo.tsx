"use client";

import { useState } from "react";
import { GateVerdict } from "@contracts";

const EXAMPLES = [
  "pip install requests",
  "pip install reqeusts",
  "pip install no-such-pkg-xyz",
];

const VERDICT_STYLE: Record<string, string> = {
  ALLOW: "bg-emerald-50 text-emerald-900 ring-emerald-200",
  REVIEW: "bg-amber-50 text-amber-950 ring-amber-200",
  BLOCK: "bg-red-50 text-red-900 ring-red-200",
};

function stripNulls(value: unknown): unknown {
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

function money(value: number): string {
  if (value === 0) return "$0";
  if (value < 0.01) return `$${value.toFixed(4)}`;
  return `$${value.toFixed(2)}`;
}

function observedLine(observed: Record<string, unknown>): string {
  return Object.entries(observed)
    .slice(0, 4)
    .map(([key, item]) => `${key}: ${typeof item === "string" ? item : JSON.stringify(item)}`)
    .join(" · ");
}

function substituteLine(command: string, verdict: GateVerdict): string | null {
  const remediation = verdict.remediation;
  if (remediation?.status !== "VERIFIED_SUBSTITUTE" || !remediation.approved_requirement) {
    return null;
  }
  const name = remediation.original.name;
  if (command.includes(name)) return command.replace(name, remediation.approved_requirement);
  return remediation.approved_requirement;
}

export function Demo() {
  const [command, setCommand] = useState(EXAMPLES[0]);
  const [checked, setChecked] = useState<string | null>(null);
  const [verdict, setVerdict] = useState<GateVerdict | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function run(next: string) {
    const trimmed = next.trim();
    if (!trimmed || pending) return;
    setPending(true);
    setError(null);
    setChecked(trimmed);
    setVerdict(null);
    try {
      const response = await fetch("/api/check", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command: trimmed }),
      });
      const body: unknown = await response.json().catch(() => null);
      if (!response.ok) {
        setError(response.status === 404 ? "The check API is not running on port 8000." : `The check returned HTTP ${response.status}.`);
        return;
      }
      const parsed = GateVerdict.safeParse(stripNulls(body));
      if (!parsed.success) {
        setError("The check returned a verdict this screen does not recognise.");
        return;
      }
      setVerdict(parsed.data);
    } catch {
      setError("The check API is not running on port 8000.");
    } finally {
      setPending(false);
    }
  }

  const shown = checked ?? command.trim();
  const safe = verdict && checked ? substituteLine(checked, verdict) : null;

  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <header className="max-w-2xl">
        <p className="font-mono text-xs uppercase tracking-[0.18em] text-stone-500">InstallGate</p>
        <h1 className="mt-2 text-3xl text-stone-950">Would you let an agent run this install?</h1>
        <p className="mt-3 text-lg text-stone-700">
          The same command, with the gate off and with the gate on. Nothing is installed.
        </p>
      </header>

      <form
        className="mt-8 flex flex-col gap-3 sm:flex-row"
        onSubmit={(event) => {
          event.preventDefault();
          void run(command);
        }}
      >
        <label className="sr-only" htmlFor="command">
          Install command
        </label>
        <input
          id="command"
          value={command}
          onChange={(event) => setCommand(event.target.value)}
          className="min-w-0 flex-1 rounded-md border border-stone-300 bg-white px-3 py-2 font-mono text-sm text-stone-950 outline-none ring-stone-950 focus:ring-2"
          spellCheck={false}
        />
        <button
          type="submit"
          disabled={pending || command.trim().length === 0}
          className="rounded-md bg-stone-950 px-4 py-2 text-sm text-stone-50 disabled:opacity-50"
        >
          {pending ? "Checking…" : "Check"}
        </button>
      </form>
      <div className="mt-3 flex flex-wrap gap-2">
        {EXAMPLES.map((example) => (
          <button
            key={example}
            type="button"
            onClick={() => {
              setCommand(example);
              void run(example);
            }}
            className="rounded-full border border-stone-300 bg-white px-3 py-1 font-mono text-xs text-stone-700 hover:border-stone-950"
          >
            {example}
          </button>
        ))}
      </div>

      <div className="mt-8 grid items-start gap-4 md:grid-cols-2">
        <section className="rounded-lg bg-stone-950 p-5 text-stone-100">
          <h2 className="font-mono text-xs uppercase tracking-[0.16em] text-stone-400">Gate off</h2>
          <p className="mt-4 text-sm text-stone-300">The agent would run this.</p>
          <pre className="mt-3 overflow-x-auto font-mono text-sm text-stone-50">{shown || "—"}</pre>
        </section>

        <section className="rounded-lg border border-stone-300 bg-white p-5">
          <h2 className="font-mono text-xs uppercase tracking-[0.16em] text-stone-500">Gate on</h2>
          {pending && <p className="mt-4 text-sm text-stone-600">Reading registry metadata. The package is not installed.</p>}
          {error && <p className="mt-4 text-sm text-red-800">{error}</p>}
          {!pending && !error && !verdict && (
            <p className="mt-4 text-sm text-stone-600">Check the command to see the verdict.</p>
          )}
          {verdict && (
            <div className="mt-4 space-y-5">
              <p className={`inline-block rounded-md px-2 py-1 font-mono text-sm ring-1 ${VERDICT_STYLE[verdict.final_verdict]}`}>
                {verdict.final_verdict}
                <span className="ml-2 font-normal text-current/80">{verdict.next_action.replaceAll("_", " ")}</span>
              </p>
              {verdict.failed_closed && verdict.final_verdict === "REVIEW" && (
                <p className="text-sm text-amber-900">A lookup failed, so this stays a review.</p>
              )}
              <p className="text-sm text-stone-600">InstallGate did not run this command.</p>

              <div>
                <h3 className="font-mono text-xs uppercase tracking-[0.14em] text-stone-500">Evidence</h3>
                {verdict.evidence.length === 0 ? (
                  <p className="mt-2 text-sm text-stone-700">No findings. The artefact is pinned.</p>
                ) : (
                  <ul className="mt-2 space-y-2">
                    {verdict.evidence.map((item) => (
                      <li key={item.id} className="text-sm">
                        <span className="font-mono text-stone-950">{item.id}</span>{" "}
                        <span className="text-stone-700">{item.kind}</span>{" "}
                        <span className="font-mono text-xs text-stone-500">{item.severity}</span>
                        <span className="mt-0.5 block text-stone-600">{observedLine(item.observed)}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <div>
                <h3 className="font-mono text-xs uppercase tracking-[0.14em] text-stone-500">Explanation</h3>
                {verdict.explanation.length === 0 ? (
                  <p className="mt-2 text-sm text-stone-700">
                    {verdict.receipt && verdict.receipt.calls.length > 0
                      ? "Every explanation sentence must cite an evidence id. None did, so this panel is empty."
                      : "A clean allow does not call the model."}
                  </p>
                ) : (
                  <ul className="mt-2 space-y-2">
                    {verdict.explanation.map((sentence) => (
                      <li key={sentence.text} className="text-sm text-stone-800">
                        {sentence.text}{" "}
                        <span className="font-mono text-xs text-stone-500">{sentence.evidence_ids.join(" ")}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <div>
                <h3 className="font-mono text-xs uppercase tracking-[0.14em] text-stone-500">Command diff</h3>
                {safe && checked ? (
                  <pre className="mt-2 overflow-x-auto font-mono text-sm">
                    <div className="text-red-800">- {checked}</div>
                    <div className="text-emerald-800">+ {safe}</div>
                  </pre>
                ) : (
                  <p className="mt-2 text-sm text-stone-700">No substitute.</p>
                )}
              </div>

              <div>
                <h3 className="font-mono text-xs uppercase tracking-[0.14em] text-stone-500">Cost receipt</h3>
                {verdict.receipt ? (
                  <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
                    <dt className="text-stone-500">This check</dt>
                    <dd className="font-mono">{money(verdict.receipt.total_cost_usd)}</dd>
                    <dt className="text-stone-500">If every call were Ultra</dt>
                    <dd className="font-mono">{money(verdict.receipt.counterfactual_all_ultra_usd)}</dd>
                    <dt className="text-stone-500">Saved</dt>
                    <dd className="font-mono">{verdict.receipt.savings_pct.toFixed(0)}%</dd>
                    <dt className="text-stone-500">Decision engine</dt>
                    <dd className="font-mono">{verdict.receipt.deterministic_only_ms} ms</dd>
                    <dt className="text-stone-500">Model calls</dt>
                    <dd className="font-mono">{verdict.receipt.calls.length}</dd>
                  </dl>
                ) : (
                  <p className="mt-2 text-sm text-stone-700">No receipt.</p>
                )}
              </div>
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
