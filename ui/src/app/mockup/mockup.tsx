"use client";

import { useState } from "react";
import {
  Banner,
  C,
  Checking,
  ConfirmLine,
  CopyButton,
  Cursor,
  Diff,
  Prompt,
  Segmented,
  StepRow,
  TerminalFrame,
  type ConfirmState,
  type Tone,
} from "../terminal";

// Sample data from the design mockup. Not live; some values are invented.
type Ev = [id: string, sev: string, src: string, text: string];
type Scenario = {
  label: string;
  verdict: "ALLOW" | "REVIEW" | "BLOCK";
  target: string;
  code?: string;
  cmd: string;
  sub: string;
  total: string;
  steps: [Tone, string, string, string][];
  evidence: Ev[];
  why: [string, string][];
  validator: string;
  fix: { source: string; from: string; to: string; note: string } | null;
  allow?: string;
  receipt: string;
  offCmd: string;
  off: [string, "" | "red" | "dim"][];
};

const SCENARIOS: Record<string, Scenario> = {
  typo: {
    label: "Typosquat", verdict: "BLOCK", target: "reqeusts", code: "P4", cmd: "pip install reqeusts", sub: "pypi · risk 0.97 · verified substitute", total: "1.84s",
    steps: [
      ["ok", "Parse target", "pypi · reqeusts · unpinned", "2 ms"],
      ["ok", "Registry metadata", "exists · first upload 2 days ago · 1 maintainer", "118 ms"],
      ["ok", "OSV.dev", "no MAL- record", "204 ms"],
      ["bad", "Typosquat check", '1 edit from "requests" (top-5k list)', "3 ms"],
      ["bad", "Policy", "P4 typosquat + new project → BLOCK", "1 ms"],
      ["ok", "Tavily (untrusted)", "0 reports in the last 30 days", "412 ms"],
      ["ok", "Nemotron Nano → Super", "3 sentences drafted", "1.06 s"],
      ["ok", "Validator", "3/3 cited · stricter-of keeps BLOCK", "2 ms"],
      ["ok", "Substitute", "requests · pinned · re-checked", "38 ms"],
    ],
    evidence: [
      ["EV-1", "hard", "policy", "typosquat match and first upload under 7 days"],
      ["EV-2", "soft", "pypi", 'Damerau-Levenshtein distance 1 from "requests"'],
      ["EV-3", "soft", "pypi", "first upload 2 days ago · 1 maintainer"],
      ["EV-4", "info", "pypi", "requests: exists · no MAL- record · pinned and hashed"],
    ],
    why: [
      ["reqeusts is one transposed letter away from requests, a top-5k package.", "EV-2"],
      ["Its first upload was 2 days ago, by a single maintainer.", "EV-3"],
      ["Rule P4 blocks a new package that imitates a popular name.", "EV-1"],
    ],
    validator: "Validator: 3 of 3 sentences cited · 0 dropped",
    fix: { source: "top-5k neighbour · re-checked [EV-4]", from: "pip install reqeusts", to: 'pip install "requests==[pinned]" --hash=sha256:[pinned]', note: "Not run. Confirm it, then run it yourself or let your agent run it." },
    receipt: "Nemotron on Nebius Token Factory · Nano 508 tok → Super 1,390 tok · $0.00059 (all-Ultra $0.00251, −76%) · Tavily 1 call",
    offCmd: "pip install reqeusts",
    off: [["Collecting reqeusts", ""], ["  Downloading reqeusts-0.1.0.tar.gz (2.1 kB)", ""], ["  Preparing metadata (setup.py) ... done", ""], ["Installing collected packages: reqeusts", ""], ["Successfully installed reqeusts-0.1.0", ""], ["", ""], ["# No check ran. setup.py executed with this shell's credentials in reach.", "red"]],
  },
  halluc: {
    label: "Hallucinated name", verdict: "BLOCK", target: "openai-agents-toolkit-pro", code: "P1", cmd: "pip install openai-agents-toolkit-pro", sub: "pypi · risk 0.99 · block", total: "1.21s",
    steps: [
      ["ok", "Parse target", "pypi · openai-agents-toolkit-pro", "2 ms"],
      ["bad", "Registry metadata", "not found on PyPI", "131 ms"],
      ["skip", "OSV.dev", "skipped: no package to look up", "–"],
      ["ok", "Typosquat check", "no near match in the top-5k list", "4 ms"],
      ["bad", "Policy", "P1 not found → BLOCK", "1 ms"],
      ["ok", "Nemotron Nano → Super", "intent extracted · 2 sentences drafted", "0.94 s"],
      ["warn", "Validator", "1/2 cited · 1 sentence dropped", "2 ms"],
      ["warn", "Substitute", "no candidate in the closed set", "9 ms"],
    ],
    evidence: [
      ["EV-1", "hard", "pypi", 'no project named "openai-agents-toolkit-pro"'],
      ["EV-2", "info", "policy", "candidate search: 0 matches in alias map or top-5k"],
    ],
    why: [["openai-agents-toolkit-pro does not exist on PyPI, so this name is unclaimed.", "EV-1"]],
    validator: "Validator: 1 of 2 sentences cited · 1 dropped (no evidence id)",
    fix: null,
    receipt: "Nemotron on Nebius Token Factory · Nano 380 tok → Super 980 tok · $0.00043 (all-Ultra $0.00184, −77%)",
    offCmd: "pip install openai-agents-toolkit-pro",
    off: [["ERROR: Could not find a version that satisfies the requirement openai-agents-toolkit-pro", "red"], ["ERROR: No matching distribution found for openai-agents-toolkit-pro", "red"], ["", ""], ["# Fails today. If someone registers this name, the next run installs their code.", "red"]],
  },
  pickle: {
    label: "Pickle model", verdict: "REVIEW", target: "acme/sentiment-small", code: "P7", cmd: "huggingface-cli download acme/sentiment-small", sub: "huggingface · risk 0.66 · review", total: "2.21s",
    steps: [
      ["ok", "Parse target", "huggingface · acme/sentiment-small", "2 ms"],
      ["warn", "Hub metadata", "pytorch_model.bin (pickle) · no .safetensors", "176 ms"],
      ["warn", "Policy", "P7 pickle-only → REVIEW", "1 ms"],
      ["ok", "Tavily (untrusted)", "0 reports in the last 30 days", "388 ms"],
      ["ok", "Nemotron Nano → Super", "risk scored 0.66", "0.71 s"],
      ["warn", "Escalate to Ultra", "REVIEW at risk 0.66 ≥ 0.60", "0.88 s"],
      ["ok", "Validator", "3/3 cited · stays REVIEW", "2 ms"],
      ["ok", "Substitute", "safetensors sibling · pinned revision", "41 ms"],
    ],
    evidence: [
      ["EV-1", "soft", "huggingface", "weights only in pytorch_model.bin (pickle)"],
      ["EV-2", "info", "huggingface", "no .safetensors file in this repo"],
      ["EV-3", "info", "huggingface", "acme/sentiment-small-safetensors lists model.safetensors"],
      ["EV-4", "info", "huggingface", "sibling: exists · revision pinned"],
    ],
    why: [
      ["This repo ships weights only as a pickle file, which can run code when loaded.", "EV-1"],
      ["There is no safetensors copy in the repo itself.", "EV-2"],
      ["A sibling repo publishes the model as safetensors.", "EV-3"],
    ],
    validator: "Validator: 3 of 3 sentences cited · 0 dropped",
    fix: { source: "safetensors sibling · re-checked [EV-4]", from: "huggingface-cli download acme/sentiment-small", to: "huggingface-cli download acme/sentiment-small-safetensors --revision [pinned]", note: "Never unpickled. Confirm the sibling is the same model before you switch." },
    receipt: "Nemotron on Nebius Token Factory · Nano 440 tok → Super 1,150 tok → Ultra 1,760 tok · $0.00278 (all-Ultra $0.00443, −37%) · Tavily 1 call",
    offCmd: "huggingface-cli download acme/sentiment-small",
    off: [["Fetching 4 files: 100%|████████████████| 4/4", ""], ["/home/dev/.cache/huggingface/hub/models--acme--sentiment-small", ""], ["", ""], ["# Downloaded. pytorch_model.bin is a pickle: torch.load() can execute code from it.", "red"]],
  },
  docker: {
    label: "Dockerfile", verdict: "BLOCK", target: "FROM php:8.3.30-apache", code: "P3", cmd: "installgate check Dockerfile", sub: "docker · risk 0.95 · verified substitute", total: "1.33s",
    steps: [
      ["ok", "Parse Dockerfile", "line 1 · FROM php:8.3.30-apache", "3 ms"],
      ["bad", "Runtime floor", "PHP 8.3.30 is below the patched floor 8.3.36", "1 ms"],
      ["bad", "Policy", "P3 below floor → BLOCK", "1 ms"],
      ["ok", "Tavily (untrusted)", "2 reports: PHP core RCE advisories", "451 ms"],
      ["ok", "Nemotron Nano → Super", "3 sentences drafted", "0.86 s"],
      ["ok", "Validator", "3/3 cited · stricter-of keeps BLOCK", "2 ms"],
      ["ok", "Substitute", "php:8.3.36-apache · digest pinned", "12 ms"],
    ],
    evidence: [
      ["EV-1", "hard", "policy", "php 8.3.30 < floor 8.3.36 (sample CVE ids)"],
      ["EV-2", "soft · web", "tavily", "2 advisories on PHP core remote code execution"],
      ["EV-3", "info", "docker hub", "php:8.3.36-apache meets the floor · digest pinned"],
    ],
    why: [
      ["The base image runs PHP 8.3.30, below the patched floor of 8.3.36.", "EV-1"],
      ["Versions below the floor are exposed to two critical PHP remote code execution flaws.", "EV-1"],
      ["Recent advisories report the same flaws (web source, unverified).", "EV-2"],
    ],
    validator: "Validator: 3 of 3 sentences cited · 0 dropped",
    fix: { source: "patched floor · re-checked [EV-3]", from: "FROM php:8.3.30-apache", to: "FROM php:8.3.36-apache@sha256:[pinned digest]", note: "Not applied. Edit line 1 of your Dockerfile, then rebuild." },
    receipt: "Nemotron on Nebius Token Factory · Nano 470 tok → Super 1,240 tok · $0.00054 (all-Ultra $0.00229, −77%) · Tavily 1 call",
    offCmd: "docker build -t app .",
    off: [["[+] Building 18.2s (9/9) FINISHED", ""], [" => [1/5] FROM docker.io/library/php:8.3.30-apache", ""], [" => exporting to image", ""], ["", ""], ["# Built. The image ships PHP 8.3.30, below the patched floor.", "red"]],
  },
  clean: {
    label: "Clean package", verdict: "ALLOW", target: "fastapi", cmd: "pip install fastapi", sub: "pypi · risk 0.00 · allow", total: "0.31s",
    steps: [
      ["ok", "Parse target", "pypi · fastapi", "2 ms"],
      ["ok", "Registry metadata", "exists · no recent maintainer change", "97 ms"],
      ["ok", "OSV.dev", "no MAL- record", "188 ms"],
      ["ok", "Typosquat check", "exact match in the top-5k list", "1 ms"],
      ["ok", "Policy", "P9 → ALLOW", "1 ms"],
      ["skip", "Nemotron", "skipped: clean ALLOW needs no model call", "–"],
      ["ok", "Pin", "version and sha256 recorded", "22 ms"],
    ],
    evidence: [], why: [], validator: "", fix: null,
    allow: 'pip install "fastapi==[pinned]" --hash=sha256:[pinned]',
    receipt: "No model calls · $0.00 · deterministic path only",
    offCmd: "pip install fastapi",
    off: [["Collecting fastapi", ""], ["  Downloading fastapi-[version]-py3-none-any.whl", ""], ["Successfully installed fastapi-[version]", ""], ["", ""], ["# Same install, but unpinned and with no evidence trail.", "dim"]],
  },
};

const OFF_COLOR = { "": "#D6DEEB", red: "#FF9B94", dim: C.dim };

export function MockupDemo() {
  const [key, setKey] = useState("typo");
  const [gate, setGate] = useState<"on" | "off">("on");
  const [confirm, setConfirm] = useState<ConfirmState>("wait");
  const d = SCENARIOS[key];
  const runCmd = d.fix?.to ?? d.allow;

  function pick(next: string) {
    setKey(next);
    setConfirm("wait");
  }

  return (
    <main className="mx-auto flex min-h-[100dvh] max-w-[1400px] flex-col gap-3 px-4 py-4 md:px-6">
      <header>
        <h1 className="m-0 text-[18px] font-semibold tracking-[-0.02em]">InstallGate</h1>
        <p className="mt-1 text-[13px] text-[#4B5563]">Sample output. Same layout as the live gate. y copies, nothing installs.</p>
      </header>
      <div className="flex flex-wrap items-end gap-6">
        <Segmented
          id="m-scenario"
          label="Scenario"
          options={Object.entries(SCENARIOS).map(([k, s]) => [k, s.label] as const)}
          value={key}
          onPick={pick}
        />
        <Segmented id="m-gate" label="Gate" options={[["on", "On"], ["off", "Off"]] as const} value={gate} onPick={setGate} danger="off" />
      </div>
      <TerminalFrame
        title={`ig ${d.cmd}`}
        scrollKey={`${key}-${gate}-${confirm}`}
        footer={
          <Prompt who="">
            ig <Cursor />
          </Prompt>
        }
      >
        {gate === "off" ? <Prompt who="">{d.offCmd}</Prompt> : <Checking command={d.cmd.replace(/^installgate check /, "")} />}
        {gate === "off" ? (
          d.off.map(([t, c], i) => (
            <div key={i} className="whitespace-pre-wrap" style={{ color: OFF_COLOR[c] }}>
              {t || " "}
            </div>
          ))
        ) : (
          <>
            <div className="mt-1">
              {d.steps.map(([tone, name, detail, ms]) => (
                <StepRow key={name} tone={tone} name={name} detail={detail} ms={ms} />
              ))}
            </div>
            <Banner verdict={d.verdict} name={d.target} code={d.code} />
            <div style={{ color: C.dim }}>
              {"  "}
              {d.sub}
            </div>
            {d.evidence.length === 0 ? (
              <div style={{ color: C.dim }}>{"  "}no findings · model skipped</div>
            ) : (
              d.evidence.map(([id, sev, src, text]) => {
                const tone = sev.startsWith("hard") ? C.bad : sev.startsWith("soft") ? C.warn : C.skip;
                return (
                  <div key={id} className="whitespace-pre-wrap">
                    <div>
                      <span style={{ color: tone }}>×</span> {text}
                    </div>
                    <div style={{ color: C.dim }}>
                      {"   ╭─[ "}
                      <span style={{ color: C.link }}>
                        {id} {sev} · {src}
                      </span>
                      {" ]"}
                    </div>
                    <div style={{ color: C.dim }}>{"   ╰──"}</div>
                  </div>
                );
              })
            )}
            {d.why.map(([text, cite]) => (
              <div key={text} style={{ color: C.skip }}>
                {"  "}note: {text} [{cite}]
              </div>
            ))}
            {d.validator ? (
              <div style={{ color: C.skip }}>
                {"  "}note: {d.validator}
              </div>
            ) : null}
            {d.fix && (
              <>
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div style={{ color: C.ok }}>
                    {"  "}help: use substitute ({d.fix.source})
                  </div>
                  <CopyButton key={key} text={d.fix.to} label="Copy" />
                </div>
                <Diff from={d.fix.from} to={d.fix.to} />
                <div style={{ color: C.dim }}>
                  {"  "}note: {d.fix.note}
                </div>
              </>
            )}
            {!d.fix && d.verdict !== "ALLOW" && (
              <>
                <div style={{ color: C.warn }}>{"  "}help: no safe substitute in the closed candidate set</div>
                <div style={{ color: C.dim }}>{"  "}note: ask a human which package was meant, then check that name</div>
              </>
            )}
            {d.allow && (
              <>
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0 break-all" style={{ color: C.ok }}>
                    {"  "}help: {d.allow}
                  </div>
                  <CopyButton key={key} text={d.allow} label="Copy" />
                </div>
                <div style={{ color: C.dim }}>{"  "}note: pinned artefact. Confirm to copy. The browser never installs.</div>
              </>
            )}
            <div style={{ color: C.dim }}>
              {"  "}note: {d.receipt} · {d.total}
            </div>
            {runCmd && (
              <ConfirmLine
                display={runCmd}
                defaultYes={d.verdict === "ALLOW"}
                state={confirm}
                onAnswer={(yes) => {
                  if (yes) void navigator.clipboard?.writeText(runCmd).catch(() => undefined);
                  setConfirm(yes ? "yes" : "no");
                }}
              />
            )}
          </>
        )}
      </TerminalFrame>
    </main>
  );
}
