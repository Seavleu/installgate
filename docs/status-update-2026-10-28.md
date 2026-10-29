# Status report

| | |
| --- | --- |
| To | InstallGate project team |
| From | Jenny, model and product |
| Date | 28 October 2026 |
| Subject | Progress as at 28 October 2026 |
| Period covered | 26 October 2026 to 28 October 2026 |
| Status | On track for a demonstration. Not yet ready to submit. |
| Next milestone | Internal submission, 30 October 2026, 18:00 NZDT |

## 1. Purpose

This note records what InstallGate can do today, what has been measured, and what remains before submission. It is for the project team. It is not a technical design note.

InstallGate checks a proposed install before anything is installed. It returns allow, review, or block, with the facts behind that decision. It does not run the package, and it does not run a suggested replacement command.

## 2. Summary

The decision engine is complete and measured. On 150 labelled cases it blocked every malicious and invented package and blocked none of the known-good packages. Explanations, cost records, and a pinned replacement command are built. They are not yet on one path that a reviewer can use from the API, the command line, and an agent tool. That path is written and pushed. It is not merged. The demonstration screen, the public address, and the submission video are not started.

## 3. Progress against the plan

| Work | State | Note |
| --- | --- | --- |
| Shared result shape, frozen 26 October | Complete | Both engineers build against the same fields. |
| Read pip, npm, Hugging Face, and Dockerfile requests | Complete | Invalid input is rejected before any lookup. |
| Look up PyPI, npm, OSV, and Hugging Face, with a local cache | Complete | A repeated lookup does not call the registry again until the cache expires. |
| Allow, review, and block rules | Complete | Rules P1 to P10. The strictest match stands. |
| PHP base images below the patched floor | Complete | Floors checked against the 21 October 2026 advisory. |
| Hold the model to the evidence | Complete | An explanation sentence without a recorded fact is dropped. The model cannot block on its own and cannot overturn a block. A failed lookup becomes a review, not an allow. |
| Confirm the model service and record tokens and latency | Complete | Nano and Super. |
| Written explanation and a cost record | Complete | The largest model is used only when a review is already high risk. |
| Recent public security reports | Complete | Taken from an approved set of sites. A page can support a review. It cannot block an install by itself. |
| Pinned replacement command | Complete | Chosen from a fixed list, by identifier. The command is shown and not run. |
| 150-case measurement, and the public write-up | Complete | Figures below. Published in the README on 28 October 2026. |
| One result from the API, the command line, and the agent tool | In review | Written and pushed on branch `T11-gate`. The pull request is not open. Not on the main line. |
| Demonstration screen | Not started | Gate off and gate on, evidence, explanation, command change, and cost. |
| Public address, spending cap, and prepared samples | Not started | Required for a reviewer who does not clone the repository. |
| Offline substitute check | Not started | Cut first if time is short. |
| Submission video and Devpost form | Not started | Due with the 30 October submission. |

## 4. What the product does today

1. It names the package in a pip install, an npm install, a Hugging Face model, or a Dockerfile base image.
2. It reads public registry records only. It does not install or import the package.
3. It blocks a name that does not exist, a package with a known malicious advisory, a new typosquat of a popular name, and a PHP image below its patched version.
4. It refers to a person the cases that are suspicious but not proven: an older typosquat, a release under 30 days old, a model that ships only pickle weights, a recent change of maintainer, or a check that could not be completed.
5. It allows a package only when nothing is wrong and the exact version and file hash are fixed. An unpinned install that merely looks fine does not pass.
6. Where the decision is not a clean allow, Nemotron on Nebius Token Factory writes an explanation. Each sentence must cite a recorded fact.
7. A smaller model does the first pass. A larger model writes the explanation. The largest model runs only for a review that already scores as high risk. Each such check records its cost, and the cost if the largest model had done the whole check.
8. For a block or a review, it can offer one pinned replacement from a closed list, for example `requests` in place of `reqeusts`. It shows the change of command and stops.

## 5. Measurement

Source: README benchmark, run on 28 October 2026 at commit `582c702`. The run uses stored registry data. It does not call the model. Full tables are in `eval/results.md`.

| Measure | Target | Result |
| --- | --- | --- |
| Malicious and invented packages blocked | at least 95% | 100% |
| Known-good packages blocked | at most 2% | 0% |
| Known-good packages sent to review | no target set | 11.4% (5 of 44) |
| Typical decision time | — | 0.02 ms |
| Slow decision time (95th percentile) | — | 0.66 ms |

The five reviews are current releases of known packages (`fastapi`, `numpy`, `django`, `pydantic`, `sqlalchemy`) requested without a version. A release under 30 days old is sent to review on purpose. None of those five was blocked.

These times and the zero model cost apply to the decision engine alone. They are not the time or the cost of a check that also writes an explanation.

Of the 50 malicious cases, 25 reconstruct the registry as it was before the package was removed. That portion shows the advisory rule is connected. It does not show the rule catching a package in the wild on the day of the run. npm is not in this measurement. An npm install is sent to review. Only the PHP version floors have been checked against the vendor advisory. Other image floors are placeholders.

## 6. Issues and risks

| Item | Effect | Response |
| --- | --- | --- |
| The shared API, command line, and agent tool are not merged | A reviewer cannot yet obtain one result from all three | Open the pull request for `T11-gate` and obtain the required approval |
| No demonstration screen or public address | The submission cannot be judged from a browser | Start these as soon as the shared check is on the main line |
| Model cost has not been measured on the 150 cases | The cost claim in the submission would be unsupported | Keep the published numbers labelled as decision-engine only until a full run exists |
| Submission is in two days | Video and form are unstarted | Cut the offline substitute check first if the date is at risk |

## 7. Work remaining before 30 October

1. Open and merge the pull request for one shared result.
2. Build the demonstration screen: the same install with the gate off and the gate on, the evidence, the explanation, the command change, and the cost.
3. Publish an address a reviewer can open without installing the project, with a spending cap.
4. Record the video, at three minutes or less, and complete the submission form.

## 8. Decision requested

None. The order above is the plan unless the team chooses to cut the demonstration screen or the public address. Cutting either one leaves the submission without a way for a judge to see the product.
