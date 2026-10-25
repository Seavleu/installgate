# validator/ — Kate

Stage 3. The model does not have the last word.

| File | Build this |
| --- | --- |
| `citations.py` | Drop any sentence that does not cite a real `EV-n` id |
| `lattice.py` | `final = max(policy, llm)` on ALLOW < REVIEW < BLOCK. LLM may raise ALLOW → REVIEW. LLM must never BLOCK or lower a verdict |
| `failclosed.py` | Any error → REVIEW. Never ALLOW on failure |

Task: T09. Tests first.
