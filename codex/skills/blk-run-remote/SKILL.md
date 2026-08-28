---
name: blk-run-remote
description: Run an isolated GPU tb_tex blk_run regression on a supported remote host, from committed-candidate transfer through log collection and guarded cleanup. Use for sanity, smoke, or nightly simulation regressions on rhel8-VM. Do not use for JasperGold/formal runs, shared-checkout execution, or unsupported password-authenticated hosts.
---

# Remote blk_run

Run the fixed remote workflow through the installed wrapper. The wrapper keeps
the candidate, remote paths, command surface, artifact collection, and cleanup
bounded so the ordinary workflow needs one reviewed entrypoint.

## Inputs and defaults

- Regression is required and must be exactly `sanity`, `smoke`, or `nightly`.
- Remote host defaults to `rhel8-VM` and currently only that host is supported.
- Candidate must be the current committed `HEAD` of
  `/Users/tibger01/Projects/Fornjot/a_gpu`.
- The `blk_run` command always uses `--build-clean --no-bsub --worker=local`
  and `--max-jobs 10`; these are not caller-configurable.
- Local artifacts are stored under
  `<repo>/private/tmp/to_persist/blk-run-remote/<run-id>/`.

`--max-jobs 10` is a concurrency limit understood by `blk_run`, not a promise
of exactly ten operating-system processes or physical CPU cores.

## Standard entrypoint

Invoke the installed wrapper directly:

```sh
/Users/tibger01/.config/codex/skills/blk-run-remote/scripts/run_remote_blk_run.sh \
  --commit <current-HEAD-sha> \
  --regression <sanity|smoke|nightly> \
  --host rhel8-VM
```

Do not prefix the command with `bash`, `zsh`, `env`, or another launcher. The
execution-policy rule matches the wrapper path as the first argument. The
`--host` option may be omitted because it defaults to `rhel8-VM`.

Use `--dry-run` to validate the candidate and print the resolved plan without
SSH, Git transfer, or remote mutation. For a live run, keep the wrapper in the
foreground and relay progress at least once per minute while it is active.

Before transfer, the live wrapper invokes the shared guarded removal helper in
idempotent mode for the exact SHA/regression worktree. It removes a retained or
stale matching worktree and branch, including a branch left after manual
worktree pruning. It refuses cleanup when a matching simulation process is
active or when the expected path is an unregistered directory.

The wrapper reuses `$transfer-git-commit-to-rhel8` for candidate transfer and
the `blk-run` mode of `$setup-gpu-repo-rhel8` for isolated worktree creation,
component preparation, and guarded removal. It then sources
`tb_tex/sourceme`, creates and enters `sim2`, runs `blk_setup`, and executes:

```sh
mkdir sim2
cd sim2
blk_setup
```

It does not depend on the user-defined `mkcdsetup` alias. The regression
command is:

```sh
blk_run --build-clean --<regression> --no-bsub --worker=local --max-jobs 10
```

It copies the complete console log plus small log/report/result files before
removing a successful run's guarded worktree. A nonzero `blk_run` result,
collection failure, or cleanup failure prints `RECOVERY_WORKTREE` and retains
the worktree. Report the host, regression, exit status, local artifact path,
and retained recovery path when present. Do not infer individual-test success
from the process status alone; inspect the collected log and result files.

Read [references/remote-workflow.md](references/remote-workflow.md) before the
first live run on a host or when recovering a retained worktree.

## Authentication boundary

`rhel8-VM` uses key-only noninteractive SSH (`BatchMode=yes`). The accepted
host surface is intentionally an allowlist, not an arbitrary hostname.

`login43.hpc01.eu03.arm.com` is reserved as a future backend and is rejected
by the current wrapper because it requires password authentication. Never
read, print, pass on a command line, or copy a password from macOS Keychain.
Add login43 support only after an approved authentication and HPC execution
design is available; do not run the local-worker workflow on a shared login
node merely by relaxing the host check.

## Knowledge lookup boundary

The installed skill and wrapper are authoritative for a standard execution.
Choosing a requested regression, defaulting the host, invoking the wrapper,
and reporting its artifacts require no Speculus, Jira, Confluence, web, or
wider repository lookup. Use internal knowledge services only when the user
explicitly requests them or a separate investigation must interpret a design,
test, or infrastructure failure not explained by the collected evidence.
