# Remote tb_tex blk_run workflow

## Standard path

Use the fixed entrypoint for ordinary runs:

```sh
/Users/tibger01/.config/codex/skills/blk-run-remote/scripts/run_remote_blk_run.sh \
  --commit <current-HEAD-sha> \
  --regression <sanity|smoke|nightly> \
  --host rhel8-VM
```

Invoke the executable directly. `--dry-run` performs all local validation and
prints the transfer ref, worktree, fixed command options, and artifact root
without contacting the remote host.

## What the wrapper enforces

1. The candidate resolves exactly to current local `HEAD`, and tracked staged
   or unstaged changes are rejected. Untracked files are not transferred.
2. The shared removal helper first cleans the exact SHA/regression worktree,
   temporary branch, and candidate ref if they remain. It refuses active
   matching simulation processes and unregistered directories.
3. The existing `transfer-git-commit-to-rhel8` helper pushes only a
   SHA-specific candidate ref to `rhel8-VM:git-transfer/c_gpu.git`.
4. The existing `setup-gpu-repo-rhel8` helper runs in its bounded `blk-run`
   mode. It fetches that ref into the remote `a_gpu` repository and creates a
   dedicated worktree named from the candidate SHA and regression. Shared
   checkouts such as `a_gpu`, `b_gpu`, or `tmp_gpu` are never reset, cleaned,
   or used as the run directory.
5. That shared setup helper sources `design/sourceme` only to enable component
   tooling, updates committed Git components in the isolated worktree, and
   verifies the `tb_tex` environment exists.
6. `run_blk_run.sh` enters
   `verification/tb_deploy/tb_tex`, sources `./sourceme` once in its run shell,
   creates and enters `sim2`, executes `blk_setup`, and launches the fixed
   local-worker command in the foreground. It does not depend on the user's
   `mkcdsetup` alias.
7. The collector copies the authoritative console log and small text/JSON/XML
   result artifacts. It deliberately excludes waveforms, databases, coverage
   stores, and other large generated data.
8. A successful run is cleaned only after the copied `run.log` is nonempty.
   Failed runs and incomplete collections retain the isolated worktree.

Two simultaneous runs of the same candidate and regression intentionally use
the same worktree name. The second run's pre-cleanup refuses to remove it when
matching simulation processes are active. Different regression types use
different worktree names.

## Fixed remote sequence

The runner implements the user's manual sequence in an isolated checkout:

```sh
cd <worktree>/verification/tb_deploy/tb_tex
source ./sourceme
mkdir sim2
cd sim2
blk_setup
blk_run --build-clean --<regression> --no-bsub --worker=local --max-jobs 10
```

The `source` command runs with nounset temporarily disabled because the
environment scripts legitimately inspect variables that may initially be
unset. Strict shell error handling is restored before `blk_run` starts.

## Artifacts and result interpretation

The local run directory contains orchestration logs (`pre-cleanup.log`,
`transfer.log`, `setup.log`, `remote-session.log`, `collect.log`, and usually
`cleanup.log`), the remote runner's `run.log`, `metadata.env`, `exit-status`,
and selected small files from `sim2`.

Treat `REMOTE_BLK_RUN_STATUS` as the command status, not a complete per-test
summary. Inspect the collected `run.log` and machine-readable result files for
the regression outcome. If the command status is nonzero, the wrapper retains
the worktree even when collection succeeds.

## Recovery

When `RECOVERY_WORKTREE` is printed:

1. Record the exact host, SHA, regression, run ID, and worktree path.
2. Check only processes that refer to that exact worktree. Do not broadly kill
   another user's or another run's simulation processes.
3. Inspect the remote `sim2` directory and the task-local `run.log` before
   retrying.
4. If only collection failed, rerun `collect_artifacts.sh` with the exact
   recorded arguments.
5. Preserve any additional requested evidence before invoking the shared
   removal helper with `--workflow blk-run --regression TYPE --yes` for that
   exact guarded path.

## Future login43 backend

`login43.hpc01.eu03.arm.com` is not enabled in this version. It currently
requires password authentication and is an HPC login node. Supporting it
requires an approved non-secret authentication mechanism plus a scheduler or
compute-node execution design. Do not retrieve Keychain credentials or simply
run `--worker=local` on the login node.
