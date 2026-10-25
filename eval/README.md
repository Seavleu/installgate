# eval/ — Kate

Benchmark. Metadata only. Do not install anything.

| File | Build this |
| --- | --- |
| `cases/malicious.jsonl` | 50 OSV MAL- cases |
| `cases/benign.jsonl` | 50 known-good packages / patched tags |
| `cases/hallucinated.jsonl` | 30 names that do not exist |
| `cases/typosquat.jsonl` | 20 near-misses (e.g. reqeusts) |
| `fixtures/` | Prompt-injection READMEs and fault cases |
| `runner.py` | Writes `results.md` |

Targets: block recall ≥ 95%, false-block ≤ 2%, ≥ 70% of checks with no model call.

Task: T13 / T17. Live network only if `LIVE_TESTS=1`.
