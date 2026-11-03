# Owner instructions

## Git workflow

Keep only `main` and `DEV` branches. Develop on `DEV`, validate changes,
then merge into `main`. Do not create task-specific branches. Track
`origin/main` and `origin/DEV`; do not force-push shared history.
See `docs/en/GIT_WORKFLOW.md` and `docs/uk/GIT_WORKFLOW.md`.

`platform/` is the current modeling system. `prototype/` is tracked in this
same repository, not a separate Git checkout or submodule.

## Builder_1: prohibited

Owner instruction, 2026-11-02: this agent MUST NOT use Builder_1 for any work.
Do not connect to it, execute commands, compile, build, package, test, inspect
status, upload/download files, or delegate work to it through another agent,
chat, controller, runner or service. Do not use its credentials or access paths.
This prohibition supersedes all earlier Builder_1 permissions and runbooks,
including the 2026-10-12 authorization and the iVINS-SERVER #323 procedure.
Only a later explicit owner instruction revoking this prohibition can permit use.
Package and qualify the server on the local AMD64 host; do not present those
checks as native ARM64 component evidence.
