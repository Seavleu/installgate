# Release (you run these)

Do this in **your** terminal, not in Cursor, so git history is yours.

## 0. Once per machine: Trusted Publishing

1. PyPI → Account → Publishing → **pending publishers** (or the `installgate` project → Publishing):
   - Owner: `Seavleu`
   - Repository: `installgate`
   - Workflow: `publish.yml`
   - Environment: `pypi`
2. GitHub repo → Settings → Environments → create **`pypi`**.
3. **Revoke** the long-lived PyPI token that was pasted in chat.

Later uploads: `gh release create vX.Y.Z` → the `publish` workflow uploads. No token in a shell.

## 1. This release (0.1.3)

From the repo root, with a clean `git status` you are happy with:

```bash
uv lock
uv sync --extra dev
uv run ruff check
uv run ruff format --check
uv run mypy
uv run pytest
uv build
```

Commit as **you**:

```bash
git add -A
git status   # no .env, no .pypirc, no .cursor/mcp.json
git commit -m "$(cat <<'EOF'
chore: packaging hygiene for 0.1.3

Changelog, extras, Trusted Publishing, issue templates, completions, man page.

EOF
)"
git push origin main
```

Tag + GitHub Release (triggers PyPI + GHCR):

```bash
git tag -a v0.1.3 -m "installgate 0.1.3"
git push origin v0.1.3
gh release create v0.1.3 --title "0.1.3" --notes-file CHANGELOG.md --generate-notes
```

If Trusted Publishing is not wired yet, one last manual upload:

```bash
# create a *new* token, do not reuse the leaked one
UV_PUBLISH_TOKEN=pypi-... uv publish
```

Install check:

```bash
uv tool install --force installgate
ig --version
```

Homebrew formula: after the sdist is on PyPI, fill `sha256` in `packaging/homebrew/installgate.rb` (command is in that file).

## Skipped on purpose

- **src/ layout** — would move every import; not this release
- **MkDocs site** — README + playbook stay the docs
- **Full SLSA** — PyPI attestations on `publish.yml` only
