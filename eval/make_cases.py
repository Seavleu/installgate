"""Regenerate the offline case set. No network: this writes fixtures, not facts.

    uv run python -m eval.make_cases

PyPI only. npm is cut from this milestone — with no vetted popular-name source
the typosquat check is switched off for npm, so every npm case would resolve to
REVIEW through a coverage gap rather than through anything under test.

The malicious cases written here are placeholders. `eval.fetch_osv_malicious`
overwrites the file with real OSV advisories; this generator exists so the other
three classes stay reproducible and so a fresh clone has a runnable benchmark.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

CASES_DIR = Path(__file__).parent / "cases"

# Matches eval.runner's FALLBACK_NOW: the ages below are relative to it.
ANCHOR = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)
SHA = "b" * 64


def ago(days: int) -> str:
    return (ANCHOR - timedelta(days=days)).isoformat()


def case(**kwargs: Any) -> dict[str, Any]:
    return kwargs


# ------------------------------------------------------------------ benign (50)
# Release dates are invented and deliberately old. `eval.verify_labels` replaces
# them with what PyPI actually reports, which is what the 7/30-day thresholds
# must be tuned against — see the review-rate-on-benign metric in results.md.
BENIGN_PYPI = [
    ("requests", "2.31.0"),
    ("urllib3", "2.2.2"),
    ("numpy", "2.0.1"),
    ("pandas", "2.2.2"),
    ("fastapi", "0.111.0"),
    ("flask", "3.0.3"),
    ("django", "5.0.7"),
    ("pydantic", "2.8.2"),
    ("httpx", "0.27.0"),
    ("sqlalchemy", "2.0.31"),
    ("click", "8.1.7"),
    ("jinja2", "3.1.4"),
    ("pyyaml", "6.0.1"),
    ("boto3", "1.34.144"),
    ("certifi", "2024.7.4"),
    ("cryptography", "42.0.8"),
    ("packaging", "24.1"),
    ("setuptools", "70.3.0"),
    ("pytest", "8.2.2"),
    ("rich", "13.7.1"),
    ("typer", "0.12.3"),
    ("uvicorn", "0.30.1"),
    ("scipy", "1.14.0"),
    ("matplotlib", "3.9.1"),
    ("pillow", "10.4.0"),
    ("scikit-learn", "1.5.1"),
    ("tqdm", "4.66.4"),
    ("attrs", "23.2.0"),
    ("six", "1.16.0"),
    ("idna", "3.7"),
    # Added when the npm cases were cut, to keep the class at 50.
    ("charset-normalizer", "3.3.2"),
    ("python-dateutil", "2.9.0"),
    ("pytz", "2024.1"),
    ("jmespath", "1.0.1"),
    ("s3transfer", "0.10.2"),
    ("wheel", "0.43.0"),
    ("filelock", "3.15.4"),
    ("platformdirs", "4.2.2"),
    ("virtualenv", "20.26.3"),
    ("tomli", "2.0.1"),
]

# Tags at or above the floor of their own branch in engine/runtime_floors.yaml.
# Those floors are unverified placeholders; these tags move with them.
BENIGN_DOCKER = [
    ("python", "3.11.9-slim"),
    ("node", "20.15.0"),
    ("php", "8.2.35"),
    ("nginx", "1.27.0"),
    ("postgres", "16.3"),
    ("redis", "7.2.5"),
    ("alpine", "3.20"),
    ("debian", "12.6"),
    ("ubuntu", "22.04"),
    ("node", "22.4.1"),
]

# ------------------------------------------------------------- hallucinated (30)
HALLUCINATED = [
    "requests-async-client",
    "fastapi-auth-toolkit",
    "pandas-dataframe-utils",
    "numpy-matrix-helper",
    "django-rest-toolkit-pro",
    "flask-jwt-complete",
    "sqlalchemy-async-orm",
    "pydantic-validators-extra",
    "httpx-retry-client",
    "openai-chat-wrapper",
    "langchain-memory-plus",
    "torch-vision-utils",
    "transformers-pipeline-helper",
    "huggingface-model-loader",
    "boto3-s3-helper-pro",
    "azure-storage-simple",
    "gcp-bigquery-client-lite",
    "redis-cache-decorator",
    "celery-task-monitor",
    "pytest-fixtures-extra",
    "mypy-strict-helper",
    "ruff-config-generator",
    "poetry-lock-resolver",
    "uvicorn-worker-manager",
    "asyncio-task-pool",
    "websocket-client-async",
    "graphql-schema-builder",
    "prometheus-metrics-helper",
    "opentelemetry-auto-tracer",
    "structlog-json-formatter",
]

# ---------------------------------------------------------------- typosquat (20)
# (lookalike, canonical, days old). Under 7 days is P4 (BLOCK); older is P5 (REVIEW).
# Every lookalike must be a near-miss of a name in the reference snapshot, or the
# case silently becomes a hallucinated one caught by P1.
TYPOSQUATS = [
    ("reqeusts", "requests", 2),
    ("requsts", "requests", 1),
    ("urlib3", "urllib3", 3),
    ("nunpy", "numpy", 2),
    ("pandsa", "pandas", 4),
    ("djano", "django", 1),
    ("flsak", "flask", 5),
    ("pydantci", "pydantic", 3),
    ("fastpai", "fastapi", 2),
    ("sqlalchmey", "sqlalchemy", 6),
    ("beatifulsoup4", "beautifulsoup4", 400),
    ("crytography", "cryptography", 300),
    ("matplotlbi", "matplotlib", 250),
    ("scikit-lean", "scikit-learn", 180),
    ("pyyaml2", "pyyaml", 200),
    # Replacing the five npm lookalikes that were cut.
    ("certfi", "certifi", 2),
    ("jinja3", "jinja2", 4),
    ("pillwo", "pillow", 1),
    ("colorma", "colorama", 220),
    ("packagin", "packaging", 260),
]

# ---------------------------------------------------------------- malicious (50)
# Placeholder names and ids. eval.fetch_osv_malicious replaces this whole file.
MALICIOUS_PLACEHOLDERS = [
    "colourama",
    "python3-dateutil",
    "jeilyfish",
    "requests-toolbelt-helper",
    "urllib3-secure",
    "pytorch-nightly-cpu",
    "django-server-tools",
    "aws-login-tool",
    "crypt-utils",
    "setup-tools-helper",
    "numpy-utils",
    "pandas-helper",
    "beautifulsoup-4",
    "pyyaml-env",
    "flask-security-utils",
    "boto3-helper",
    "openai-api-client",
    "telegram-bot-helper",
    "discord-token-utils",
    "env-loader-util",
    "fastapi-auth-helper",
    "sqlalchemy-utils-ext",
    "pillow-simd-fast",
    "scipy-helper",
    "matplotlib-utils",
    "torch-cuda-helper",
    "keras-layers-extra",
    "nltk-corpus-loader",
    "spacy-model-fetch",
    "gensim-word2vec-util",
    "xgboost-trainer",
    "lightgbm-helper",
    "catboost-utils",
    "shap-explainer-lite",
    "optuna-tuner-pro",
    "mlflow-logger-util",
    "wandb-sync-helper",
    "dvc-remote-util",
    "airflow-dag-builder",
    "prefect-flow-helper",
    "dagster-asset-util",
    "luigi-task-helper",
    "kedro-pipeline-util",
    "great-expectations-lite",
    "pandera-schema-util",
    "polars-io-helper",
    "duckdb-query-util",
    "pyarrow-dataset-helper",
    "fsspec-cache-util",
    "s3fs-credentials-helper",
]


def build_benign() -> list[dict[str, Any]]:
    rows = []
    n = 1
    for name, version in BENIGN_PYPI:
        rows.append(
            case(
                id=f"benign-{n:03d}",
                label="benign",
                ecosystem="pypi",
                command=f"pip install {name}=={version}",
                expected_verdict="ALLOW",
                facts={
                    "exists": True,
                    "latest_version": version,
                    "latest_sha256": SHA,
                    "first_upload": ago(2500),
                    "latest_upload": ago(120),
                    "maintainers": ["core-team"],
                },
                osv={"malicious": False, "mal_ids": []},
                verified_source=False,
                notes="Dates are invented; run eval.verify_labels for real ones.",
            )
        )
        n += 1
    for image, tag in BENIGN_DOCKER:
        rows.append(
            case(
                id=f"benign-{n:03d}",
                label="benign",
                ecosystem="docker",
                command=f"FROM {image}:{tag}",
                expected_verdict="ALLOW",
                facts={
                    "exists": True,
                    "latest_version": tag,
                    "latest_sha256": SHA,
                    "first_upload": ago(900),
                    "latest_upload": ago(60),
                    "maintainers": ["official"],
                },
                verified_source=False,
                notes=(
                    "Tag sits at or above its branch floor. Both the tag and the floor "
                    "in engine/runtime_floors.yaml are unverified and move together."
                ),
            )
        )
        n += 1
    return rows


def build_hallucinated() -> list[dict[str, Any]]:
    return [
        case(
            id=f"hallucinated-{i:03d}",
            label="hallucinated",
            ecosystem="pypi",
            command=f"pip install {name}",
            expected_verdict="BLOCK",
            facts={"exists": False},
            verified_source=False,
            notes="Must still 404 on the day of the run; eval.verify_labels confirms.",
        )
        for i, name in enumerate(HALLUCINATED, start=1)
    ]


def build_typosquat() -> list[dict[str, Any]]:
    rows = []
    for i, (bad, canonical, days) in enumerate(TYPOSQUATS, start=1):
        rows.append(
            case(
                id=f"typosquat-{i:03d}",
                label="typosquat",
                ecosystem="pypi",
                command=f"pip install {bad}",
                expected_verdict="BLOCK" if days < 7 else "REVIEW",
                facts={
                    "exists": True,
                    "latest_version": "0.1.0",
                    "latest_sha256": SHA,
                    "first_upload": ago(days),
                    "latest_upload": ago(days),
                    "maintainers": ["unknown"],
                },
                osv={"malicious": False, "mal_ids": []},
                verified_source=False,
                notes=f"Lookalike of {canonical!r}; {days} days old. Facts are invented.",
            )
        )
    return rows


def build_malicious() -> list[dict[str, Any]]:
    return [
        case(
            id=f"malicious-{i:03d}",
            label="malicious",
            ecosystem="pypi",
            command=f"pip install {name}",
            expected_verdict="BLOCK",
            facts={
                "exists": True,
                "latest_version": "0.0.1",
                "latest_sha256": SHA,
                "first_upload": ago(5),
                "latest_upload": ago(5),
                "maintainers": ["unknown"],
            },
            osv={"malicious": True, "mal_ids": [f"MAL-PLACEHOLDER-{i:03d}"]},
            registry_state="simulated_pre_removal",
            verified_source=False,
            notes=(
                "PLACEHOLDER. Not a real advisory. Run eval.fetch_osv_malicious to "
                "replace this file with records from ossf/malicious-packages."
            ),
        )
        for i, name in enumerate(MALICIOUS_PLACEHOLDERS, start=1)
    ]


def main() -> int:
    CASES_DIR.mkdir(parents=True, exist_ok=True)
    for filename, rows in [
        ("benign.jsonl", build_benign()),
        ("malicious.jsonl", build_malicious()),
        ("hallucinated.jsonl", build_hallucinated()),
        ("typosquat.jsonl", build_typosquat()),
    ]:
        with (CASES_DIR / filename).open("w", encoding="utf-8", newline="\n") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"{filename}: {len(rows)} cases")
    print("\nPyPI and container images only. No Hugging Face cases exist, so P7")
    print("(hf_pickle) is not covered by this benchmark - see results.md.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
