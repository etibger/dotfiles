---
name: jaspergold-rhel8-fpv
description: Orchestrate an isolated JasperGold FPV run for GPU Formal fb_tex_flt on the rhel8-VM host, from committed-candidate transfer through bounded proof and local artifact collection. Use for remote RHEL8 formal validation; do not use for simulation-only work or shared-checkout execution.
---

# JasperGold RHEL8 FPV

This is a hierarchical composition skill. It coordinates other skills; it does
not duplicate their safety and debugging procedures.

## Defaults and required inputs

- SSH target: `rhel8-VM` using key-only authentication.
- Formal environment: `verification/formal/fb_tex_flt`.
- FTRun target: `tex_flt`.
- Proof concurrency: 6 jobs/slots.
- Active proof duration: 30 minutes.
- Local artifacts:
  `<repo>/private/tmp/jaspergold-rhel8-fpv/<run-id>/`.

Allow the caller to override target, jobs, and duration. State that jobs/slots
do not guarantee the same number of OS processes or physical CPU cores.

## Composition order

1. Use `$transfer-git-commit-to-rhel8` to push the committed candidate and
   record its SHA and closest origin ancestor.
2. Use `$setup-gpu-repo-rhel8` to create and prepare a dedicated hash-named
   worktree from `a_gpu`. Do not use a lock or alter a shared checkout.
3. Read and apply `$jaspergold-local-fpv`, including its
   `references/workflow.md` and first-CEX wrapper. Supply the requested jobs and
   proof duration explicitly.
4. Collect selected proof artifacts locally with
   [scripts/collect_artifacts.sh](scripts/collect_artifacts.sh).
5. For a counterexample, invoke `$fpv-vcd-analysis` on the copied VCD.

Request authorization immediately before externally mutating actions unless
the current user request already authorizes them. Keep the foreground SSH
session observable, report progress at least once per minute, and do not leave
Jasper/FTRun jobs running after an aborted trial.

## Remote run

Copy the local Jasper wrapper and
[scripts/run_fpv.sh](scripts/run_fpv.sh) into the worktree's task-specific
`private/tmp/jaspergold-rhel8-fpv/<run-id>/` directory. Execute `run_fpv.sh` on
the VM with the exact worktree, run ID, job count, and proof limit. The script
keeps the normal target Tcl hooks, applies the active proof limit through the
wrapper, passes the job cap through `-slots`, and runs in the foreground.

Read [references/remote-workflow.md](references/remote-workflow.md) before the
first run on a host or when using the intentional-CEX trial.

## One-minute skill trial

Only when the user authorizes an intentionally failing smoke assertion:

- keep the default six-job cap and use `1m` active proof time, unless the caller
  requests a different trial concurrency;
- apply [assets/intentional_cex.patch](assets/intentional_cex.patch) only to the
  isolated worktree after setup;
- append [assets/intentional_cex_target.yaml](assets/intentional_cex_target.yaml)
  to `BLKFORMAL_CONFIG` and run target `tex_flt_codex_trial`; this disables
  ProofMaster orchestration and the proof cache for a predictable fresh smoke
  run while retaining the six-slot cap;
- request the QuietTrace with property glob
  `*codex_trial_intentional_cex`;
- confirm `git status` shows the trial change and never commit or push it;
- require a nonempty raw or QuietTrace VCD, copy it locally, and analyze it;
- remove the remote worktree after preserving requested artifacts.

An expected CEX proves that the orchestration and artifact path work. It says
nothing about the correctness of the candidate RTL.
