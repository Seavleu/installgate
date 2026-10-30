# InstallGate

Pre-install trust gate for coding agents. You pass one `pip install` or `npm install` command. InstallGate reads **registry metadata only** (never installs), applies a YAML policy, and returns **ALLOW**, **REVIEW**, or **BLOCK**.

A clean ALLOW is pinned (`name==version`) and skips the model. BLOCK needs hard deterministic evidence. The model may explain; it cannot override policy.

## Install

Python 3.11+.

```bash
uv tool install installgate
uv tool update-shell
```

If you use pipx:

```bash
pipx install installgate
```

Then `ig` is on your PATH from any directory (same idea as installing Node, then typing `node`). If a previous `ig` is in the way:

```bash
uv tool install --force installgate
```

```bash
ig --version
```

## Use

`--no` means check only — it never runs pip/npm.

```bash
ig --no pip install requests         # ALLOW, pin, no model
ig --no pip install reqeusts         # BLOCK typo; substitute is pinned requests
ig --no pip install no-such-pkg-xyz  # BLOCK, no substitute
```

Exit codes: `0` ALLOW, `1` REVIEW, `2` BLOCK.

Optional keys in the environment (or a `.env` in the current directory):

- `NEBIUS_API_KEY` — explanations on REVIEW/BLOCK (NVIDIA Nemotron on Nebius Token Factory). ALLOW does not need it.
- `TAVILY_API_KEY` — recent web evidence (untrusted, never a BLOCK).

## MCP

```bash
uvx --from installgate python -m mcp_server.server
```

Tool: `check_install`. Argument: `command`.

## Docs

GitHub: [Seavleu/installgate](https://github.com/Seavleu/installgate) (full README, policy, demo).
Live page: [installgate.installgate-ui.workers.dev](https://installgate.installgate-ui.workers.dev)

License: Apache-2.0
