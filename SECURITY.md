# Security

## Report a vulnerability

Use [GitHub Security Advisories](https://github.com/Seavleu/installgate/security/advisories/new) on this repository.

Do **not** file a public issue for:

- leaked API keys or tokens
- a way to make InstallGate execute third-party code
- a way to turn a policy BLOCK into ALLOW

We aim to acknowledge reports within 7 days.

## What this project guarantees

InstallGate reads registry **metadata only**. It must never `pip install` / `npm install` / `import` a checked package as part of a check. The model cannot issue BLOCK and cannot lower a verdict. See `AGENTS.md`.

## Secrets

Keys come from environment variables or a local `.env` that is gitignored. Rotate any token that was pasted into chat, email, or a ticket.
