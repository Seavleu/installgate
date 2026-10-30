# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project versions with [PEP 440](https://peps.python.org/pep-0440/).

## [0.1.3] — 2026-10-30

### Added

- `ig --version` / `ig -V`
- `ig completion bash|zsh|fish`
- `installgate-mcp` console script
- Optional extras: `[server]` (FastAPI/Uvicorn), `[tavily]`
- PyPI classifiers, keywords, Changelog URL
- man page `ig(1)`
- GitHub issue templates, Dependabot, Trusted Publishing workflow

### Changed

- Default wheel no longer depends on FastAPI/Uvicorn/Typer. HTTP API: `uv sync --extra server` or `pip install installgate[server]`
- sdist excludes `eval/` and `ui/`

## [0.1.2] — 2026-10-30

### Added

- `--version` handling in the source tree (not on PyPI 0.1.1)

### Fixed

- `installgate --version` was parsed as `pip install --version`

## [0.1.1] — 2026-10-30

### Changed

- PyPI long description is `docs/pypi.md` (install-first), not the GitHub README

## [0.1.0] — 2026-10-30

### Added

- First PyPI release: `ig` / `installgate` CLI, MCP `check_install`, policy P1–P10

[0.1.3]: https://github.com/Seavleu/installgate/releases/tag/v0.1.3
[0.1.2]: https://github.com/Seavleu/installgate/releases/tag/v0.1.2
[0.1.1]: https://github.com/Seavleu/installgate/releases/tag/v0.1.1
[0.1.0]: https://github.com/Seavleu/installgate/releases/tag/v0.1.0
