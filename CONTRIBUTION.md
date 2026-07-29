# Contribution workflow

This repository uses one canonical Git branch: `main`.

- Do not create local or remote feature branches.
- Do not open pull requests.
- Make scoped commits directly on `main`.
- After relevant checks pass, push directly to `origin/main`.
- Stage files explicitly and never include unrelated working-tree changes.
- If an old branch exists, integrate it into `main` only when this can be done safely, then remove it.
- If branch protection or permissions reject a direct push, report the blocker; do not create a branch or pull request.

This policy applies to maintainers, contributors, automation, and coding agents.
