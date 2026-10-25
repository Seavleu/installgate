# remediate/ — Jenny

Stage 4. Safe substitute. You never run the command.

| File | Build this |
| --- | --- |
| `candidates.py` | Closed set only: alias map, top-n neighbours, HF safetensors sibling, patched docker tag |
| `pinning.py` | Pin version + sha256 |
| `diff.py` | `- bad` / `+ safe` command diff |
| `sandbox.py` | Stretch: Token Factory sandbox, network off |

The model picks a candidate **by id**. It must not type a package name. Re-check the pick with the engine before you show it.

Task: T10.
