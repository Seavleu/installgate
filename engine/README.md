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
| `policy.yaml` + `policy.py` | Rules P1–P10. Strictest match wins |
| `runtime_floors.yaml` | Patched version floors (e.g. php) |
| `cache.py` | SQLite with TTL |
| `data/` | Dated top-5k names for typosquat |

## P10: a check that could not run

A check that cannot run does not stay silent. It emits a soft `check_unavailable`
evidence record with the cause in `observed["reason"]`, and rule **P10** turns any
such record into REVIEW. P9 (ALLOW) needs zero evidence, so a gap can never read as
a clean result, and being soft it can never produce a BLOCK (FR-09).

| `observed["reason"]` | When |
| --- | --- |
| `no_floor_for_branch` | The tag is on a release branch with no recorded floor |
| `floating_tag` | `latest`, `bookworm`, or `8.3` / `8.3-apache` with no patch release |
| `digest_only` | A Dockerfile reference with no tag |
| `image_not_in_table` | No floors recorded for this image |
| `typosquat_unsupported_ecosystem` | No vetted popular-name set (npm) |

Tasks: T03, T04, T05, T06, T22. Tests first. Mock HTTP with respx. No live network in unit tests.

Timeouts and host allowlists on every client. Fail closed to REVIEW on errors.
