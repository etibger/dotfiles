---
name: jaspergold-rhel8-fpv
description: Orchestrate an isolated JasperGold FPV run for GPU Formal fb_tex_flt on the rhel8-VM host, from committed-candidate transfer through bounded proof and local artifact collection. Use when asked to run fb_tex_flt remotely; standard execution is self-contained and needs no specification lookup. Do not use for simulation-only work or shared-checkout execution.
---

# JasperGold RHEL8 FPV

This is a hierarchical composition skill. It coordinates other skills; it does
not duplicate their safety and debugging procedures.

## Defaults and required inputs

- SSH target: `rhel8-VM` using key-only authentication.
- Formal environment: `verification/formal/fb_tex_flt`.
- FTRun target: `tex_flt` for the normal one-command workflow.
- Proof concurrency: 6 jobs/slots.
- Active proof duration: 30 minutes.
- Local artifacts:
  `<repo>/private/tmp/jaspergold-rhel8-fpv/<run-id>/`.

Allow the caller to override jobs and duration. Keep the normal wrapper target
fixed to `tex_flt`; use the separately reviewed trial procedure when a
different target is required. State that jobs/slots do not guarantee the same
number of OS processes or physical CPU cores.

## Normal one-command entrypoint

For an ordinary committed-candidate run, invoke the installed wrapper directly:

```sh
/Users/tibger01/.config/codex/skills/jaspergold-rhel8-fpv/scripts/run_remote_fpv.sh \
  --commit <current-HEAD-sha> --jobs 6 --proof-limit 30m
```

Do not prefix this command with `bash`, `zsh`, `env`, or another launcher: the
execution-policy rule matches the wrapper path as the first argument. The
wrapper accepts only a commit SHA, a 1--10 slot cap, and a proof duration from
1 minute through 24 hours. It fixes the local repository, SSH target, transfer
ref naming, remote worktree root, formal target, helper scripts, artifact path,
and cleanup operation. The transfer ref includes the candidate's 12-character
SHA to prevent different concurrent candidates from overwriting one another.
The wrapper also requires the requested candidate to equal the repository's
current `HEAD`.

Use `--dry-run` to validate the local candidate and print the resolved plan
without SSH, Git transfer, or remote mutation. A live run streams setup and
proof output, creates the final property reports, collects selected artifacts,
and removes the guarded worktree only after the copied `run.log` and both
property-summary files are nonempty. If collection or validation fails, it
prints `RECOVERY_WORKTREE` and retains the isolated worktree.

Use the component commands below only for manual recovery or for the explicitly
authorized intentional-CEX trial. Keeping the standard workflow behind this
single fixed-purpose entrypoint avoids separate approvals for its internal
SSH, transfer, staging, collection, and guarded cleanup commands.

## Knowledge lookup boundary

Treat the installed skill and its fixed-purpose wrapper as the authoritative
operational procedure for a standard run. Invoking the wrapper, choosing the
caller-requested job count and proof limit, locating its output, and reporting
the generated property summary do not depend on internal design knowledge.

For that standard execution path, do not query Speculus, Jira, Confluence, web
search, or other knowledge services, and do not search the wider repository to
rediscover the invocation. Perform only the local preflight needed by the
wrapper, then invoke it directly. This is an explicit exception for executing
this controlled workflow, not a general exception to repository knowledge
policy.

Use a knowledge service only when the user explicitly requests it or when a
separate task requires interpreting an unexpected property, architecture, or
design result that this workflow and its generated reports do not explain.

## Internal composition order

1. Use `$transfer-git-commit-to-rhel8` to push the committed candidate and
   record its SHA and closest origin ancestor.
2. Use `$setup-gpu-repo-rhel8` to create and prepare a dedicated hash-named
   worktree from `a_gpu`. Do not use a lock or alter a shared checkout.
3. Read and apply `$jaspergold-local-fpv`, including its
   `references/workflow.md` and first-CEX wrapper. Supply the requested jobs and
   proof duration explicitly.
4. After FTRun finishes, run the deterministic property-summary stage from
   [scripts/summarize_fpv_results.py](scripts/summarize_fpv_results.py). Require
   `fpv_property_summary.rpt` and `fpv_property_summary.json`; report assertion
   passes, CEX failures, unresolved assertions, covered properties, and
   unreachable or unresolved covers. Treat the proof report as authoritative
   because FTRun can exit zero when assertions have CEXs. Run this stage with a
   task-local Python 3.12 environment created by `uv`, following the GPU
   repository's Python-version pinning; never use the RHEL8 system Python.
5. Collect selected proof artifacts locally with
   [scripts/collect_artifacts.sh](scripts/collect_artifacts.sh).
6. For a counterexample, invoke `$fpv-vcd-analysis` on the copied VCD.

Request authorization immediately before externally mutating actions unless
the current user request already authorizes them. Keep the foreground SSH
session observable, report progress at least once per minute, and do not leave
Jasper/FTRun jobs running after an aborted trial.

## Remote run

Copy the local Jasper wrapper,
[scripts/summarize_fpv_results.py](scripts/summarize_fpv_results.py), and
[scripts/run_fpv.sh](scripts/run_fpv.sh) into the worktree's task-specific
`private/tmp/jaspergold-rhel8-fpv/<run-id>/` directory. Execute `run_fpv.sh` on
the VM with the exact worktree, run ID, job count, and proof limit. The script
keeps the normal target Tcl hooks, applies the active proof limit through the
wrapper, passes the job cap through `-slots`, runs in the foreground, and then
creates `<remote-task-dir>/report-venv` with `uv` and Python 3.12 before the
proof. It uses that environment to write the two aggregate property-summary
files even when the proof contains CEXs. Its `UV_CACHE_DIR` is the task-local
`<remote-task-dir>/uv-cache`, so the report setup does not pollute the user's
home directory or a tracked worktree path.

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
