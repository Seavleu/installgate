# tests/

- Kate: `engine/`, `validator/` — write the failing test first.
- Jenny: `tests/test_token_factory.py` (T02), `tests/test_router.py` (T07), `tests/test_tavily.py` (T08), `tests/test_remediate.py` (T10), `tests/test_gate.py` (T11).
- No live network. Mock with respx.
- `eval/` live runs only with `LIVE_TESTS=1`.
