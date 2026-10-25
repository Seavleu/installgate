#!/usr/bin/env bash
# InstallGate: one-time GitHub setup.
# Creates labels, gate milestones, issues T01..T20, a Projects (kanban) board, and links them.
#
# Usage:
#   gh auth login                       # once
#   gh auth refresh -s project          # once: lets gh manage Projects
#   ./setup-github.sh OWNER/REPO        # e.g. ./setup-github.sh jcode/installgate
#   DRY_RUN=1 ./setup-github.sh OWNER/REPO   # print commands only
#   PROJECT_NUMBER=3 ./setup-github.sh OWNER/REPO   # use a board you already created (number from its URL)
#
# Safe to re-run for labels and milestones. Re-running creates duplicate issues, so run the issue step once.
set -euo pipefail

REPO="${1:?usage: ./setup-github.sh OWNER/REPO}"
OWNER="${REPO%%/*}"
DRY="${DRY_RUN:-0}"

run() { if [[ "$DRY" == "1" ]]; then printf '[dry-run] %q ' "$@"; echo; else "$@"; fi; }

echo "== Labels"
label() { run gh label create "$1" --color "$2" --description "$3" --repo "$REPO" --force; }
label "owner:A"        "1f6feb" "Engineer A: core logic"
label "owner:B"        "8250df" "Engineer B: model and product"
label "owner:both"     "6e7781" "Shared delivery"
label "area:contracts" "d4c5f9" "contracts/"
label "area:engine"    "c2e0c6" "engine/"
label "area:validator" "c2e0c6" "validator/"
label "area:router"    "fef2c0" "router/"
label "area:remediate" "fef2c0" "remediate/"
label "area:api"       "bfdadc" "mcp_server/: HTTP, CLI, MCP"
label "area:ui"        "bfdadc" "ui/"
label "area:eval"      "c5def5" "eval/"
label "area:infra"     "e4e669" "Repo, CI, hosting"
label "area:docs"      "e4e669" "README, video, submission"
label "stretch"        "fbca04" "Cut first if time runs short"
label "blocked"        "d73a4a" "Waiting on something"

echo "== Milestones (gates; due times are end of gate in NZDT, stored as UTC)"
milestone() {
  if [[ "$DRY" == "1" ]]; then echo "[dry-run] milestone: $1 due $2"; return; fi
  if gh api "repos/$REPO/milestones?state=all&per_page=100" --jq '.[].title' | grep -Fxq "$1"; then
    echo "exists: $1"
  else
    gh api "repos/$REPO/milestones" -f title="$1" -f due_on="$2" -f description="$3" >/dev/null && echo "created: $1"
  fi
}
milestone "G1 Contracts frozen"         "2026-10-26T10:59:00Z" "contracts/ merged and tested; Nano and Super smoke test logs tokens and latency"
milestone "G2 Engine and validator"     "2026-10-27T10:59:00Z" "CLI returns a full GateVerdict for pip, HF and Dockerfile with no model call"
milestone "G3 Integrated demo"          "2026-10-28T10:59:00Z" "Router, Tavily, MCP tool and UI work end to end on sample runs"
milestone "G4 Feature freeze"           "2026-10-29T10:59:00Z" "Benchmark results written; no new features after this"
milestone "G5 Submission ready"         "2026-10-29T23:00:00Z" "Video uploaded, README complete, fresh-clone test passes, repo public"
milestone "G6 Submit"                   "2026-10-30T05:00:00Z" "Devpost submission clicked, not saved as a draft"

echo "== Project board"
if [[ -n "${PROJECT_NUMBER:-}" ]]; then
  PROJECT="$PROJECT_NUMBER"
  echo "using existing project #$PROJECT (not creating a new one)"
  if [[ "$DRY" != "1" ]]; then
    gh project link "$PROJECT" --owner "$OWNER" --repo "$REPO" || true
  fi
elif [[ "$DRY" == "1" ]]; then
  PROJECT=0; echo "[dry-run] gh project create --owner $OWNER --title InstallGate"
else
  PROJECT=$(gh project create --owner "$OWNER" --title "InstallGate" --format json --jq '.number')
  gh project link "$PROJECT" --owner "$OWNER" --repo "$REPO"
  echo "project #$PROJECT created and linked to $REPO"
fi

echo "== Issues T01..T20"
# id | title | labels | milestone | depends on | done when
TASKS=$(cat <<'EOF'
T01|Public repo, Apache-2.0 LICENSE, .env.example, CI with secret scan|owner:both,area:infra|G1 Contracts frozen|none|Repo is public and the licence is detected
T02|Token Factory smoke test; resolve model ids from /v1/models|owner:B,area:router|G1 Contracts frozen|T01|Tokens, latency and model ids logged
T03|Freeze contracts/ and generate TypeScript from the Python schema|owner:A,area:contracts|G1 Contracts frozen|none|Contract tests pass; both engineers approved
T04|Parsers and input validation for pip, npm, Hugging Face, Dockerfile|owner:A,area:engine|G2 Engine and validator|T03|Fuzz tests pass; no network call on invalid input
T05|Registry, OSV and Hugging Face clients with SQLite cache|owner:A,area:engine|G2 Engine and validator|T03|Warm-cache run makes no external call
T06|Deterministic checks, evidence, YAML policy P1-P9, Dockerfile floor table|owner:A,area:engine|G2 Engine and validator|T04, T05|Policy unit tests pass
T07|Router: Nano extraction, Super explanation, Ultra on REVIEW >= 0.6, receipts|owner:B,area:router|G2 Engine and validator|T02, T03|Per-call cost and the all-Ultra counterfactual logged
T08|Tavily search and extract on allowlisted domains as untrusted evidence|owner:B,area:router|G2 Engine and validator|T07|Never produces hard evidence
T09|Validator: citation stripper, verdict lattice, fail-closed|owner:A,area:validator|G2 Engine and validator|T03|Lattice and fault-injection tests pass
T10|Closed candidate sets, pinning and command diff|owner:B,area:remediate|G3 Integrated demo|T06, T09|Model-invented names never appear
T11|HTTP API, CLI and MCP check_install returning one contract|owner:B,area:api|G3 Integrated demo|T03|Same verdict from all three entry points
T12|UI: Gate OFF / Gate ON replay, evidence panel, diff panel, cost receipt|owner:B,area:ui|G3 Integrated demo|T03|Aha moment reached in under 2 minutes
T13|150-case benchmark, injection and fault fixtures, eval/results.md|owner:A,area:eval|G4 Feature freeze|T06, T07, T09|One command reproduces all metrics
T14|Hosting, demo URL, rate limits, spending cap, pre-warmed samples|owner:B,area:infra|G3 Integrated demo|D-03 decided|Public URL works with no login
T15|STRETCH: network-off sandbox check of a pinned substitute|owner:B,area:remediate,stretch|G4 Feature freeze|T10, Sandboxes access|Result records that egress was denied
T16|Integration, bug fixing, feature freeze|owner:both,area:infra|G4 Feature freeze|T10-T14|Gate G4 passed
T17|README: Nemotron and Nebius section, developer feedback, responsible use|owner:both,area:docs|G4 Feature freeze|T07|Reviewed by the other engineer
T18|Record and edit the video, captions, upload to YouTube as public|owner:both,area:docs|G5 Submission ready|T16|3 minutes or less
T19|Fresh-clone test, outside-person dry run, Devpost form filled|owner:both,area:docs|G5 Submission ready|T17, T18|Gate G5 passed
T20|Submit on Devpost|owner:both,area:docs|G6 Submit|T19|Gate G6 passed
EOF
)

while IFS='|' read -r id title labels ms deps done; do
  body=$(printf '**Task:** %s\n\n**Depends on:** %s\n\n**Done when:** %s\n\n**Definition of done:** CI green, tests cover the change, contract unchanged or reviewed, docs updated if behaviour changed.\n\nSpec: docs/prd-ssd.md, section 13.' "$id" "$deps" "$done")
  if [[ "$DRY" == "1" ]]; then
    echo "[dry-run] issue: $id $title | $labels | $ms"
    continue
  fi
  url=$(gh issue create --repo "$REPO" --title "$id $title" --body "$body" --label "$labels" --milestone "$ms")
  gh project item-add "$PROJECT" --owner "$OWNER" --url "$url" >/dev/null
  echo "created $id -> $url"
done <<< "$TASKS"

echo
echo "Done. Finish in the browser (gh cannot do these):"
echo "  1. Project > Settings > Status field: add 'In review' between 'In Progress' and 'Done'."
echo "  2. Project > New view > Board, grouped by Status. Optional: a Table view grouped by Milestone."
echo "  3. Project > Workflows: turn on 'Auto-add to project' (this repo), 'Item closed' -> Done, 'Pull request merged' -> Done."
echo "  4. Repo > Settings > Branches: protect main (require a pull request, 1 approval, status checks)."