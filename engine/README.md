# engine/ — Kate

Stage 1. Deterministic. Zero model calls. Metadata only — do not install or import the package.

| File | Build this |
| --- | --- |
| `parsers.py` | Parse pip / npm / HF repo id / Dockerfile FROM |
| `clients/pypi.py` | GET pypi.org JSON |
| `clients/npm.py` | GET registry.npmjs.org |
| `clients/osv.py` | POST api.osv.dev (MAL- records) |
| `clients/huggingface.py` | GET huggingface.co model file list |
| `checks.py` | exists, age, maintainers, osv_mal, typosquat, hf_format, runtime_floor |
| `evidence.py` | Hashed Evidence with ids `EV-1`, `EV-2`, … |
| `policy.yaml` + `policy.py` | Rules P1–P9. Strictest match wins |
| `runtime_floors.yaml` | Patched version floors (e.g. php) |
| `cache.py` | SQLite with TTL |
| `data/` | Dated top-5k names for typosquat |

Tasks: T03, T04, T05, T06. Tests first. Mock HTTP with respx. No live network in unit tests.

Timeouts and host allowlists on every client. Fail closed to REVIEW on errors.
