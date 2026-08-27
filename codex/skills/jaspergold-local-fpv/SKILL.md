---
name: jaspergold-local-fpv
description: Run, bound, monitor, restore, and debug local GPU Formal JasperGold FPV/FTRun sessions, including proof-job limits, first-CEX handling, QuietTrace VCD export, and proof/IPVS/IPDS reports. Use for local or Docker-hosted Jasper/FTRun work; do not use for simulation-only debug or non-Jasper formal tools.
---

# JasperGold Local FPV

Use this skill to leave a local formal run reproducible, resource-bounded, and
with useful failure artifacts.

## Run parameters

Treat proof concurrency and proof duration as explicit independent inputs:

- `max_jobs`: a positive integer passed to `ftrun -slots` or the equivalent
  Jasper/FTS job control. It caps proof-job concurrency, not exact OS process or
  CPU use.
- `proof_limit`: a positive duration such as `60s`, `10m`, or `2h`, applied to
  the active Jasper proof or FTS prove strategy. It is not the whole-session
  wall-clock limit.

If the caller supplies either value, preserve it. Otherwise choose a
conservative value from host memory and the target configuration and state the
choice. The `$jaspergold-rhel8-fpv` composition supplies defaults of six jobs
and 30 minutes; its smoke trial keeps six jobs and supplies one minute.

## Before running

1. Read the repository's `AGENTS.md` and the formal environment's `sourceme`,
   target YAML, and target Tcl. Preserve their setup and hooks.
2. Check for an existing Jasper/FTRun/container process before starting
   another run. Do not leave a background proof running after the task ends.
3. Use a task-specific run directory. In the `a_gpu` repository, put every
   temporary wrapper, configuration, log, and run under
   `private/tmp/<task-name>/`; never use repository `tmp/`, `/tmp`, or
   `/private/tmp` for agent-created artifacts.
4. Choose the workflow:
   - Use foreground batch FTRun for automation and bounded validation. Start
     with the ordinary target before adding a replacement Tcl or derived YAML.
   - Use GUI/manual proof for interactive exploration or as the fallback after
     one fresh batch retry stalls during licence checkout.
   - Restore an existing saved JDB when a long run already contains the needed
     result.

## Non-obvious rules

- `ftrun -slots N` limits proof-job concurrency. It is not a guaranteed cap of
  exactly N OS processes or N physical CPUs, especially with ProofMaster or
  Jasper orchestration enabled.
- FTRun's outer `-time_limit` does not bound a `-local` proof. Bound active
  Jasper proof time with `tool_config.jg.run_limit`, an FTS prove strategy's
  `run_limit`, `::fts::prove -run_limit`, or Jasper
  `set_prove_time_limit`/`prove -time_limit`.
- Use `-auto_run` for a batch target that should prove properties. Without it,
  FTRun can stop after elaboration.
- Use `-save on_failure` and retain the normal FTS final hook. Otherwise a CEX
  may exist only in a live process and normal reports/JDB output can be lost.
- A raw VCD is the reliable fallback. QuietTrace replot is synchronous and can
  take substantial memory and time; never save before replot finishes.
- Prefer restoring a saved session and querying the live trace over repeatedly
  exporting very large VCDs.
- A log ending at `checking out 'jasper_fpv'` records a stalled checkout, not a
  licence denial. GUI and batch startup differ, but both are known to work; use
  the bounded triage in the workflow before changing licence variables or
  formal configuration.

## Detailed procedures

Read [references/workflow.md](references/workflow.md) before launching or
modifying a run. It contains:

- the local Docker, GUI, and foreground batch commands;
- the two distinct concurrency controls and three distinct time limits;
- a tested first-CEX/QuietTrace flow;
- session restore and interactive CEX analysis;
- proof, resource, IPVS, and IPDS report generation;
- cleanup and common failure modes.

For a GPU Formal target that needs best-effort stop-on-first-CEX plus raw and
QuietTrace VCDs, copy
[assets/stop_on_first_cex_vcd.tcl](assets/stop_on_first_cex_vcd.tcl) into the
repository's task-specific temporary directory, set `FTRUN_BASE_TCL` to the
target's ordinary Tcl, and invoke it with `ftrun -tcl`. The asset preserves the
base hooks; do not source it as an additional Tcl after FTS has started.

When a trial or focused debug must retain a particular failed property, set
`FTRUN_CEX_PROPERTY_GLOB` to a Tcl glob matching its full property name. The
raw FTS VCD can still follow FTS discovery order; the custom QuietTrace export
must use the matching property or report that the requested CEX was absent.

## Completion checks

- Confirm from the Jasper session log that the requested proof limit and job
  limit were applied.
- Record whether the run completed, timed out, was stopped on CEX, or was
  killed by memory/resource limits. Never report an infrastructure kill as a
  successful proof.
- For a failure, verify that at least one VCD or a saved `db*/jdb` exists and is
  nonempty.
- Report the exact run directory and the most useful report/VCD/JDB paths.
