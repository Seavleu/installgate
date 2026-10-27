# contracts/ — both engineers

`contracts.py` and `contracts.ts` are the shared API shape.

**FROZEN as of gate G1 (2026-10-26).** Field names, types, and enum values in `contracts.py` are final. Kate and Jenny both build against this shape starting now — the API, CLI, terminal output, and UI must all read the same field names, or the same package install will show different results depending on which surface you look at.

Rules from here on:

- No renaming, adding, or removing a field, enum value, or model on a feature branch without saying so in the PR title (e.g. `fix(contracts): ...`).
- Any such change needs review from **both** engineers before merge — see `.github/CODEOWNERS`.
- If a field turns out to be wrong, open an issue and discuss before touching the file. Do not silently rename and let the other person find out from a failing build.
