# remediate/ — Jenny

Stage 4. Safe substitute. You never run the command.

| File | Build this |
| --- | --- |
| `candidates.py` | Closed set only: alias map, top-n neighbours, HF safetensors sibling, patched docker tag |
| `pinning.py` | Pin version + sha256 |
| `diff.py` | `- bad` / `+ safe` command diff |
| `sandbox.py` | Stretch: Token Factory sandbox, network off |

The model picks a candidate **by id** (`C1`, `C2`, …). A package name it types is discarded and does not appear in the diff. The pick is shown only after the engine re-check ids are passed in. This folder does not run the command and does not call the engine.

```bash
uv run --no-sync pytest tests/test_remediate.py -v
```

Task: T10.
