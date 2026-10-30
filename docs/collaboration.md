# How we land a task

One task, one branch, one pull request. `main` changes only when that pull request merges.

Jenny is **Seavleu** (`router/`, `remediate/`, `mcp_server/`, `ui/`). Kate is **katebres** (`engine/`, `validator/`, `eval/`). `contracts/` and `docs/` need both of you. Issue numbers match the task ids: T07 is `#7`.

The board, labels, and milestones already exist. Do not run `setup-github.sh` again.

## Rules

- Branch name is the task, then a short tail: `T07-router`. Not your name.
- Commit subject ends with the task id: `[T07]`.
- The pull request body starts with `Closes #7`. That is what marks the card Done after the merge.
- Open the pull request, then drag the card to **In review**. Opening the pull request does not move the card. Do not drag it to Done.
- `main` takes a pull request, one approval, and green checks named `python`, `ui`, and `gitleaks`. No force-push. One ruleset is enough. Leave the older “branch protection rule” screen off so the rules do not stack.
- Never commit `.env`.

**Screenshot:** the ruleset on `main` (pull request required, 1 approval, the three checks).

![Ruleset on main](screenshots/01-ruleset.png)

## Steps

Do this from the repo root. The example is T07. The next task uses the same commands with its own id.

### 1. Start from an updated main

```bash
git checkout main
git pull
git checkout -b T07-router
```

`git pull` happens here, before the new branch. Once you are on the task branch with uncommitted edits, stay there. Switching back to `main` or pulling again parks the work on the wrong branch.

**Screenshot:** the terminal on `T07-router`.

![On the task branch](screenshots/02-branch.png)

### 2. Do the work and run its test

The folder README names the command. For T07:

```bash
uv run --no-sync pytest tests/test_router.py -v
```

A pass is `7 passed`. These tests mock HTTP. They do not read `.env` and they do not call a model. `uv run python -m router.smoke` is the T02 ping only. It does not run `route`.

**Screenshot:** the pytest summary.

![T07 tests passed](screenshots/03-pytest.png)

### 3. Commit the task files

Leave out `.env` and `AGENTS.md` unless that task changed them.

```bash
git add router/README.md router/prompts/explain.txt router/prompts/extract.txt \
  router/receipt.py router/tiers.py router/token_factory.py tests/test_router.py
git commit -m "$(cat <<'EOF'
feat(router): route Nano, Super, and conditional Ultra with a cost receipt [T07]

Ultra runs only for policy REVIEW at risk >= 0.6. The receipt logs each call and the all-Ultra counterfactual.

EOF
)"
```

The first line is the subject. The blank line before the second sentence matters. Without it, Git glues the body onto the subject.

**Screenshot:** `git log -1` or the commit on GitHub.

![Commit subject with the task id](screenshots/04-commit.png)

### 4. Push the branch

```bash
git push -u origin HEAD
```

This sends `T07-router`. It does not change `main`.

### 5. Open the pull request

https://github.com/Seavleu/installgate/pull/new/T07-router

Title, same as the commit subject:

```text
feat(router): route Nano, Super, and conditional Ultra with a cost receipt [T07]
```

Body:

```text
Closes #7

## What changed
route calls Nano, then Super. Ultra runs only when policy is REVIEW and risk >= 0.6. The receipt logs each call and the all-Ultra counterfactual. A clean ALLOW makes no model call.

## How to check it
uv run --no-sync pytest tests/test_router.py -v

## Checklist
- [x] Tests cover the change
- [x] contracts/ unchanged
- [x] No package is installed and no new host was added
- [x] router/README.md updated
- [ ] CI is green (ruff, mypy, pytest, secret scan)
```

Check the CI box after the three jobs are green. Drag issue **#7** to **In review**.

**Screenshot:** the pull request description, with `Closes #7` visible.

![Pull request body](screenshots/05-pull-request.png)

**Screenshot:** the T07 card in **In review**.

![Kanban In review](screenshots/06-kanban.png)

### 6. Review, then merge

The other person runs the “How to check it” command, reads the diff, and approves. Merge only when `python`, `ui`, and `gitleaks` are green.

**Screenshot:** the three green checks.

![Green CI checks](screenshots/07-checks.png)

The merge puts the commits on `main`. `Closes #7` closes the issue. If the “pull request merged → Done” workflow is on, the card moves to Done. If the issue was already closed before the pull request, the card does not move. That happened to `#2`. Drag it to Done after the merge in that case.

### 7. Delete the branch and start the next task

```bash
git checkout main
git pull
git branch -d T07-router
git checkout -b T08-tavily
```

Also delete `T07-router` on GitHub (the merged pull request has a button, or turn on “automatically delete head branches”). The commits stay on `main`. The next task gets a new branch.

## Kate, same loop

Your next open task is **#3**, T03, on a branch named `T03-contracts`. Same commit shape, with `[T03]` and `Closes #3`. Jenny reviews that pull request. A change under `contracts/` needs both names on the pull request.
