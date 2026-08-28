---
name: blk-run-remote
description: Run an isolated GPU tb_tex blk_run regression on rhel8-VM, retaining the exact worktree and producing a normalized result summary. Use for sanity, smoke, or nightly simulation; do not use for formal runs or shared checkouts.
---

# Remote blk_run

Run the bounded remote workflow through
[scripts/run_remote_blk_run.sh](scripts/run_remote_blk_run.sh). It transfers
the current committed candidate through RHEL8 `push_gpu`, creates an isolated
worktree, runs the requested regression, collects small evidence, writes a
normalized summary, and retains the remote worktree.

## Fixed execution contract

- Host: key-authenticated `rhel8-VM`.
- Candidate: current committed `HEAD`; tracked changes are rejected.
- Regression: exactly `sanity`, `smoke`, or `nightly`.
- Local artifacts:
  `<repo>/private/tmp/to_persist/blk-run-remote/<run-id>/`.
- Large simulation artifacts remain in the remote worktree.

The remote runner sources `tb_tex/sourceme` once, creates `sim2`, runs
`blk_setup`, and executes:

```sh
blk_run --build-clean --<regression> --set-lsf-mem-limit 12000 \
  --no-bsub --no-bsub-build --worker=local --max-jobs 2
```

Do not add `--max-fail`; each regression's configured default remains in
force.

## Entrypoint and result

```sh
~/.config/codex/skills/blk-run-remote/scripts/run_remote_blk_run.sh \
  --commit <current-HEAD-sha> --regression sanity
```

Invoke the installed path directly. Use `--dry-run` for local-only validation.
For a live run keep it in the foreground and relay progress while it is
active. Require `simulation-summary.json` and report its classification,
all per-test records, captured failure details, EAP triage URLs, and exact
retained worktree. The collector includes `sim2/logs_tests/cache.sqlite`; the
summary opens it read-only and emits each test's name, seed, status, substatus,
remote log path, and original `blk_val` replay command in deterministic order.
It cross-checks those records against both the last terminal `SIMU-RES` verdict
and `sim2/regression.json`, while preserving `*_error.json` signatures for
failures. Missing or inconsistent canonical or per-test evidence is `ERROR`,
never a clean run. A nonzero regression is a failed branch even when evidence
collection succeeds.

No pre-run or post-run cleanup is automatic. A pre-existing exact worktree is
a safe stop; inspect it before an explicit cleanup or retry. Read
[references/remote-workflow.md](references/remote-workflow.md) for recovery.
