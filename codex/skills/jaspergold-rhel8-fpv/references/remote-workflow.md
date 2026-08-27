# Remote fb_tex_flt workflow

## Preflight

1. Confirm `ssh -o BatchMode=yes rhel8-VM true`.
2. Confirm no active process already refers to the new worktree path.
3. Record candidate SHA, chosen origin base, worktree, requested jobs, and
   active proof duration.
4. Ensure the RHEL8 VM has enough memory. Six FTS slots are a concurrency cap;
   Jasper orchestration may create helper processes and use substantially more
   memory.

The RHEL8 system is a dedicated VM, not an HPC login node. Do not generalize
this local-execution procedure to a shared login host; use the approved compute
allocation or scheduler there.

## Stage the wrapper and runner

Create only the task-specific remote directory below the isolated worktree:

```text
<worktree>/private/tmp/jaspergold-rhel8-fpv/<run-id>/
```

Copy these two files into it:

- `jaspergold-local-fpv/assets/stop_on_first_cex_vcd.tcl`
- `jaspergold-rhel8-fpv/scripts/run_fpv.sh`

The proof output is created below `<run-id>/work/fts_run_<target>/`; `run.log`
is written beside `work/`.

## Execute and monitor

For the normal requested run:

```sh
bash <remote-task-dir>/run_fpv.sh \
  --worktree <worktree> --run-id <run-id> \
  --target tex_flt --jobs 6 --proof-limit 30m
```

Keep the SSH process in the foreground. Inspect output for elaboration errors,
the effective run limit, proof start, resource kills, first CEX shutdown, final
reporting, VCD export, and JDB save. A nonzero FTRun result can be the expected
property failure; classify it from reports and logs rather than the exit code
alone.

## Trial-only intentional CEX

Before source generation, apply the patch from the worktree root:

```sh
git apply --check <intentional_cex.patch>
git apply <intentional_cex.patch>
```

Then rerun `make sources`, execute with `--jobs 6 --proof-limit 1m`, and verify
that the failing property name contains `codex_trial_intentional_cex`. If that
property is absent or treated as an assumption, the trial is invalid even if a
different property fails.

For the skill smoke test, also stage `intentional_cex_target.yaml` and run:

```sh
bash <remote-task-dir>/run_fpv.sh \
  --worktree <worktree> --run-id <run-id> \
  --target tex_flt_codex_trial --jobs 6 --proof-limit 1m \
  --config-fragment <remote-task-dir>/intentional_cex_target.yaml \
  --cex-property-glob '*codex_trial_intentional_cex'
```

The temporary target disables orchestration because the ordinary `tex_flt`
target can let ProofMaster fan out beyond the intuitive meaning of FTRun
slots. Even with orchestration disabled, call six a proof-job concurrency cap,
not a guarantee of exactly six OS processes.

## Artifacts and cleanup

Copy VCDs, `run.log`, proof reports, result JSON, and replay command files with
`collect_artifacts.sh`. Do not copy the potentially large JDB unless requested.
After local inspection confirms the files are usable, stop remaining processes
and invoke the guarded worktree-removal script from
`$setup-gpu-repo-rhel8`.
