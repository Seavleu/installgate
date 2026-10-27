"""Add the Hugging Face and unpinned-benign cases. ONLINE for `hf` — run by hand, never in CI.

    uv run python -m eval.add_cases hf --dry-run         # list what it would fetch and change
    uv run python -m eval.add_cases hf                   # fetch metadata, write cases
    uv run python -m eval.add_cases unpinned --dry-run   # offline either way

Metadata only. Nothing is downloaded, loaded or imported: the Hugging Face call is
`GET https://huggingface.co/api/models/{repo_id}`, which returns the file list and
the commit sha, and the weights themselves are never requested.

The candidate repos below are NOT trusted labels. The live run reads each repo's
file list and keeps a candidate only when it really is what the list claims
(safetensors only, or pickle only). A candidate that is not is skipped and
reported, never relabelled. Spares exist so a repo that changed does not leave
the benchmark short.

`unpinned` needs no network: it writes `pip install <name>` cases with
`verified_source: false`, and `eval.verify_labels` then fills in the real
registry dates (online, with its own --dry-run).

To keep the benchmark at 150 cases, each subcommand removes the same number of
pinned benign PyPI cases that it adds. None of them is a placeholder (all 40 were
verified against PyPI); they are the most redundant ones, since every one of
them exercises the same P9 path.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from engine.clients import UpstreamError, get_json
from engine.clients.huggingface import model_url, summarise

CASES_DIR = Path(__file__).parent / "cases"
HF_FILE = CASES_DIR / "huggingface.jsonl"
BENIGN_FILE = CASES_DIR / "benign.jsonl"

WANT = 5

# Unconfirmed guesses. The fetch decides what each one really is.
SAFETENSORS_CANDIDATES = [
    "Qwen/Qwen2.5-0.5B",
    "HuggingFaceTB/SmolLM2-135M",
    "microsoft/phi-2",
    "Qwen/Qwen2-0.5B",
    "stabilityai/stablelm-2-1_6b",
    "google/gemma-2-2b",
    "HuggingFaceTB/SmolLM2-360M",
]
PICKLE_ONLY_CANDIDATES = [
    "facebook/opt-125m",
    "facebook/opt-350m",
    "EleutherAI/gpt-neo-125m",
    "EleutherAI/pythia-70m",
    "bigscience/bloom-560m",
    "facebook/bart-base",
    "google/flan-t5-small",
    "xlnet/xlnet-base-cased",
    "albert/albert-base-v2",
    "openai/clip-vit-base-patch32",
]

UNPINNED = [
    "fastapi",
    "requests",
    "numpy",
    "flask",
    "django",
    "pydantic",
    "httpx",
    "sqlalchemy",
    "pytest",
    "rich",
]

# Removed to make room, 10 per subcommand. All are pinned benign PyPI cases.
DROP_FOR_HF = [f"benign-{n:03d}" for n in range(20, 30)]
DROP_FOR_UNPINNED = [f"benign-{n:03d}" for n in range(30, 40)]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), "utf-8")


def drop_cases(ids: list[str]) -> list[str]:
    rows = read_jsonl(BENIGN_FILE)
    present = [r["id"] for r in rows if r["id"] in ids]
    write_jsonl(BENIGN_FILE, [r for r in rows if r["id"] not in ids])
    return present


def classify(facts: dict[str, Any]) -> str:
    if not facts.get("exists"):
        return "missing"
    if facts.get("has_pickle") and not facts.get("has_safetensors"):
        return "pickle_only"
    if facts.get("has_safetensors") and not facts.get("has_pickle"):
        return "safetensors_only"
    return "mixed"


def hf_case(number: int, repo: str, kind: str, facts: dict[str, Any], stamp: str) -> dict[str, Any]:
    safe = kind == "safetensors_only"
    return {
        "id": f"hf-{number:03d}",
        "label": "benign" if safe else "hf_pickle",
        "ecosystem": "huggingface",
        "command": repo,
        "expected_verdict": "ALLOW" if safe else "REVIEW",
        "facts": facts,
        "verified_source": True,
        "notes": (
            "Safetensors only, pinned by the API's model sha."
            if safe
            else "Pickle weights and no safetensors file: rule P7."
        ),
        "verified_at": stamp,
        "verified_by": "huggingface_api",
    }


async def fetch_repo(client: httpx.AsyncClient, repo: str) -> dict[str, Any]:
    return summarise(await get_json(client, model_url(repo), allow_404=True))


async def run_hf(dry_run: bool) -> int:
    print(
        f"candidates: {len(SAFETENSORS_CANDIDATES)} safetensors, "
        f"{len(PICKLE_ONLY_CANDIDATES)} pickle"
    )
    print("requests (GET, metadata only, host huggingface.co):")
    for repo in SAFETENSORS_CANDIDATES + PICKLE_ONLY_CANDIDATES:
        print(f"  {model_url(repo)}")
    print(f"would write {HF_FILE.relative_to(CASES_DIR.parent.parent)} (up to {WANT}+{WANT} cases)")
    print(f"would remove from benign.jsonl: {', '.join(DROP_FOR_HF)}")
    if dry_run:
        print("dry run: no network, nothing written")
        return 0

    stamp = datetime.now(UTC).isoformat()
    picked: dict[str, list[tuple[str, dict[str, Any]]]] = {
        "safetensors_only": [],
        "pickle_only": [],
    }
    async with httpx.AsyncClient() as client:
        for repo in SAFETENSORS_CANDIDATES + PICKLE_ONLY_CANDIDATES:
            try:
                facts = await fetch_repo(client, repo)
            except UpstreamError as exc:
                print(f"  SKIP {repo}: {exc}")
                continue
            kind = classify(facts)
            want = "safetensors_only" if repo in SAFETENSORS_CANDIDATES else "pickle_only"
            if kind != want:
                print(f"  SKIP {repo}: expected {want}, the API says {kind}")
            elif len(picked[kind]) >= WANT:
                print(f"  spare {repo}: {kind}")
            else:
                print(f"  keep {repo}: {kind}, sha {str(facts.get('sha'))[:12]}")
                picked[kind].append((repo, facts))

    short = [k for k, v in picked.items() if len(v) < WANT]
    if short:
        print(f"NOT WRITTEN: fewer than {WANT} confirmed for {short}; add candidates and rerun")
        return 1

    rows: list[dict[str, Any]] = []
    for kind in ("safetensors_only", "pickle_only"):
        for repo, facts in picked[kind]:
            rows.append(hf_case(len(rows) + 1, repo, kind, facts, stamp))
    write_jsonl(HF_FILE, rows)
    removed = drop_cases(DROP_FOR_HF)
    print(f"wrote {len(rows)} cases; removed {len(removed)} benign cases: {', '.join(removed)}")
    return 0


def run_unpinned(dry_run: bool) -> int:
    existing = read_jsonl(BENIGN_FILE)
    last = max(int(r["id"].split("-")[1]) for r in existing)
    print("would add to benign.jsonl (no network, verified_source=false until eval.verify_labels):")
    for offset, name in enumerate(UNPINNED, start=1):
        print(f"  benign-{last + offset:03d}  pip install {name}")
    print(f"would remove from benign.jsonl: {', '.join(DROP_FOR_UNPINNED)}")
    if dry_run:
        print("dry run: nothing written")
        return 0

    rows = [r for r in existing if r["id"] not in DROP_FOR_UNPINNED]
    for offset, name in enumerate(UNPINNED, start=1):
        rows.append(
            {
                "id": f"benign-{last + offset:03d}",
                "label": "benign",
                "ecosystem": "pypi",
                "command": f"pip install {name}",
                "expected_verdict": "ALLOW",
                "facts": {"exists": True},
                "osv": {"malicious": False, "mal_ids": []},
                "verified_source": False,
                "notes": (
                    "Unpinned install. The registry resolves it to the latest release; "
                    "run eval.verify_labels for the real dates."
                ),
            }
        )
    write_jsonl(BENIGN_FILE, rows)
    print(
        f"wrote {len(UNPINNED)} cases; removed {len(DROP_FOR_UNPINNED)}: "
        f"{', '.join(DROP_FOR_UNPINNED)}"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("what", choices=["hf", "unpinned"])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.what == "hf":
        return asyncio.run(run_hf(args.dry_run))
    return run_unpinned(args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
