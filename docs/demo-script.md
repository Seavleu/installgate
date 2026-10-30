# Demo script — what to say, what to point at

Repo root. Big font. `--no` so nothing installs. If it asks `Y/n`, press **n**.

Do not paste `--hash` into `pip3`. Show the pin; do not run it.

---

## Open (10s)

> InstallGate sits in front of `pip` and `npm`. Metadata only — we never install the package. Policy decides. The model explains. It cannot override a BLOCK.

---

## Beat 1 — clean ALLOW (25s)

```bash
ig --no pip install requests
```

**Say:** An agent typed unpinned `requests`. Watch the stages.

| Point at | Why |
|---|---|
| `pypi · requests · unpinned` | Input has no version. |
| `exists · latest 2.34.2` | Registry only. No download. |
| `no MAL- record` | OSV. This is the slow line (~1.4s cold). |
| `Tavily … skipped: clean result` | No web search on a clean package. |
| `P9 → ALLOW` | Policy. Not the model. |
| `skipped: clean ALLOW needs no model call` | **No GPU. $0.** |
| `success: ALLOW requests==2.34.2` | Gate pinned it. |
| `help: pip install requests==2.34.2 --hash=sha256:2a0d60c1…` | Copy-paste pin. Do not run `--hash` in this pip. |
| `no model · $0 · 1.88s` | Receipt. |

> Unpinned in, pinned out. The agent may install that pin. Not the original line.

---

## Beat 2 — cache (15s)

```bash
ig --no pip install requests
```

**Say:** Same command again.

| Point at | Why |
|---|---|
| `OSV.dev … 0ms` | Cache. Not another 1.4s. |
| `Registry … 18ms` | Cache. |
| `no model · $0 · 0.04s` | **~47× faster.** Repeats are free. |

> First check pays PyPI and OSV. Every later agent call is 40 milliseconds.

---

## Beat 3 — typo + substitute (40s) ← stop here if short

```bash
ig --no pip install reqeusts
```

**Say:** This is the attack. One letter wrong. Gate OFF, pip installs whatever is on that name.

| Point at | Why |
|---|---|
| `✖ Registry … not found` | `reqeusts` is not on PyPI. |
| `P1 → BLOCK` | Hard evidence. Model cannot undo this. |
| `error[P1]: BLOCK reqeusts` | Verdict. |
| `× not found` / `EV-1 hard · pypi` | Deterministic. |
| `help: use substitute (alias map · re-checked EV-2)` | Closed set. Model did not invent the name. |
| `- pip install reqeusts` | Would-have-run. |
| `+ pip install requests==2.34.2` | Safe pin. Same hash as beat 1. |
| `Nano … → Super … · $0.00029` | Model explained. Policy already BLOCKed. |

> The agent does not run the minus line. Human or agent confirms the plus line. We never type a package name.

---

## Beat 4 — hallucinated name (20s)

```bash
ig --no pip install no-such-pkg-xyz
```

**Say:** Agents invent package names.

| Point at | Why |
|---|---|
| `P1 → BLOCK · risk 1.00` | Same rule as the typo. |
| `▲ Substitute … no safe substitute` | Nothing in the closed set. |
| `help: no safe substitute` | Stop. Ask a human. Do not search for a “better” name. |
| `Nano … → Super …` | Model still talks. Policy still BLOCK. |

> If the JSON ever shows `llm_verdict: ALLOW` next to `policy_verdict: BLOCK`, point at **stricter-of → BLOCK**. Policy wins.

---

## Optional — npm (20s)

Run as **two** lines. Do not put `# comments` on the same line.

```bash
ig --no npm install lodash
ig --no npm install totally-fake-npm-xyz
```

| Command | Point at | Say |
|---|---|---|
| `lodash` | `P9 → ALLOW` and a `@version` pin | Famous name is not automatically REVIEW. Exists + pin. |
| `totally-fake-npm-xyz` | `P1 → BLOCK` | Missing npm name is a hard stop. |

Skip `express` live. Tavily can add a news snippet and turn it into REVIEW. Do not explain that in the room.

---

## Close (10s)

> Three entry points, one verdict: CLI, HTTP, MCP `check_install`. We do not sit on the install path — the agent has to call us. A Cursor rule or `eval "$(ig hook)"` is how you make that the default. Metadata only. Model never holds authority.

Page if the projector is easier: https://installgate.installgate-ui.workers.dev  
Same three commands. **Y copies the pin. It does not install.** If the page errors, stay on the terminal.

---

## Do not

- Demo `FROM php:…` or Hugging Face (not on this CLI).
- Demo `pip install requests numpy` or `uv add` unless you want an abort.
- Let pip actually run.
- Apologise for REVIEW on lodash if this `ig` ALLOWs it — that was the old MCP.
