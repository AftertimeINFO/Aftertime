# Git workflow

The canonical repository is https://github.com/AftertimeINFO/Aftertime.git.
It has two branches: `main` for integrated changes and `DEV` for development.
Use these exact names. Start and finish development on `DEV`.

```sh
git switch DEV
git pull --ff-only origin DEV
# Implement, validate, then commit explicit changed paths.
git push origin DEV
git switch main
git pull --ff-only origin main
git merge --no-ff DEV
git push origin main
git switch DEV
git merge --ff-only main
git push origin DEV
```

If `main` advances independently, merge `origin/main` into `DEV` and validate
before integration. Never force-push shared history. A PR, when used, goes
from `DEV` to `main`; retain `DEV` after merging.

## Source layout

- `platform/`: current Model Lab, including the BPMN editor, backend and tests.
- `prototype/`: earlier prototype, tracked as ordinary files in this repository.
  Its original Git history is retained by the consolidation merge. It is not
  a submodule and needs no separate Git remote or credentials.
- `prototype/.openai/hosting*.json`: historical hosting configuration, not a
  Git dependency. Git consolidation does not change or deploy the hosted site.

The superseded platform snapshot is retained as a merge parent, while the
current platform implementation remains authoritative.

During the 2026-11-03 consolidation, the original local prototype checkout,
including dependencies and generated files, was preserved outside the repository
at `../Archive/Aftertime-prototype-original-20261103`. It is a local backup,
not a development checkout or an additional remote to synchronize.
