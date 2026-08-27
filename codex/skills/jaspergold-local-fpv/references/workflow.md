# Local JasperGold/FTRun workflow

This reference targets ARM GPU Formal environments built around FTRun/FTS and
Cadence JasperGold. Commands and configuration names were checked against the
`a_gpu` GPU Formal integration and the `fb_tex_flt` target. Adapt target and
path names, but preserve the target's ordinary Tcl hooks.

## Contents

1. Host and container setup
2. Target discovery
3. GUI/manual proof
4. Foreground batch proof
5. CPU/job and time controls
6. Stop on first CEX and export VCD
7. Restore and inspect an existing run
8. Reports and run artifacts
9. Resource and correctness pitfalls
10. Internal references

## 1. Host and container setup

First check whether the selected Docker endpoint is reachable:

```sh
docker info
```

On this Mac, if Docker is unavailable because Colima is not running, start the
existing profile with the resources needed by local Jasper proofs:

```sh
colima start --cpu 10 --memory 20 --disk 200
```

Do not restart or reconfigure Colima when `docker info` already succeeds. After
starting it, rerun `docker info` before launching the project container.

Run the local wrapper from the `a_gpu` repository root; it uses the current
directory as the workspace and mounts it at `/gpu`:

```sh
../../notes/docker-run-custom xcelium_jaspergold_blkformal
```

Before launch, confirm that `SSH_AUTH_SOCK` names a live socket. Do not hard-code
a WezTerm or macOS agent path because it changes between sessions.

Batch mode does not need X11 access. For GUI mode on this Mac, the known-working
setup is `xhost +` before launching the container. That grants broad access, so
use it only when the GUI is required and revoke it with `xhost -` after the
container exits.

Inside the container:

```sh
cd /gpu/verification/formal/fb_tex_flt
source ./sourceme
```

The current FPV target is `tex_flt`; older references to `flt_top` are stale.

## 2. Target discovery

After sourcing the environment:

```sh
ftrun -list
ftrun -h
```

Inspect the effective configuration before a costly run:

```sh
ftrun tex_flt -dump_target_cfg
```

When redirecting the dump in `a_gpu`, write it under a task-specific
`/gpu/private/tmp/<task-name>/` directory. Also inspect:

- `verification/formal/fb_tex_flt/sourceme`
- `verification/formal/fb_tex_flt/scripts/flt.yaml`
- `verification/formal/fb_tex_flt/scripts/flt.tcl`

The `-tcl` option replaces the target Tcl. A wrapper passed with `-tcl` must
source the normal target Tcl itself or it will discard common setup, reporting,
and final-save hooks.

## 3. GUI/manual proof

For `fb_tex_flt`, this is the known-working interactive flow and the fallback
when a fresh batch retry still stalls during licence checkout. From the
repository root, launch the wrapper in an interactive terminal:

```sh
../../notes/docker-run-custom xcelium_jaspergold_blkformal
```

Then, inside its login shell:

```sh
cd verification/formal/fb_tex_flt
source ./sourceme
ftrun -local tex_flt &
```

That is the exact human-operated flow. When Codex launches it, preserve the
same target, GUI mode, sourced environment, and working directory, but direct
the generated run into the repository-local temporary area:

```sh
mkdir -p /gpu/private/tmp/<task-name>
ftrun tex_flt -local \
  -build_dir /gpu/private/tmp/<task-name>/fts_run_tex_flt &
```

Wait for the Jasper GUI and Tcl prompt. These are Jasper Tcl commands, not
container-shell commands:

```tcl
set_proofgrid_max_local_jobs 2
set_engine_mode auto
prove -all -bg
```

For a bounded validation, set the default proof limit immediately before the
`prove` command:

```tcl
set_prove_time_limit 10m
prove -all -bg
```

`set_proofgrid_max_local_jobs 2` is the direct Jasper local-job cap used in the
known-working `fb_tex_flt` GUI flow. Increase it only when memory permits. An
equivalent one-command bounded proof is:

```tcl
prove -all -time_limit 10m -bg
```

Generate a text property summary at any useful checkpoint:

```tcl
report -summary -results -force -task . -file results.rpt
```

### GUI QuietTrace and VCD

Use the full task-qualified property name when more than one task exists:

```tcl
set prop {<full_property_name>}
visualize -violation -property $prop -new_window
visualize -quiet true -window visualize:0
visualize -replot -bg -window visualize:0 -prompt
visualize -save -force -vcd /gpu/private/tmp/<task-name>/cex.vcd \
  -window visualize:0
```

The `-prompt` form waits for the GUI replot interaction. Save only after the
QuietTrace replot completes.

## 4. Foreground batch proof

Batch mode is the default for automated validation. Start with the ordinary
target and an explicit `-build_dir`; no GUI licence precheck is needed. Add a
custom Tcl or derived YAML target only after that works, so each failure has one
new variable.

Run automated proofs in the foreground so Codex can monitor and terminate them.
From the sourced formal environment, make the independent controls explicit:

```sh
FPV_MAX_JOBS=2
FPV_PROOF_LIMIT=10m
export FTRUN_RUN_LIMIT="$FPV_PROOF_LIMIT"
ftrun tex_flt -local -batch -auto_run \
  -slots "$FPV_MAX_JOBS" -save on_failure
```

Use `-slots 6` when six parallel proof jobs are intentional and the container
has enough memory. One or two slots are safer for local debug on a memory-limited
Docker Desktop instance.

A fully local FTRun spelling from the current BlkFormal CLI is:

```sh
ftrun tex_flt -batch -local -job_submission local
```

`-slots 0` also forces local submission with one job per engine. It does not
mean unlimited jobs.

### Isolated run directory

From the repository root on the host, copy the reusable wrapper into the only
workspace visible inside the container:

```sh
mkdir -p private/tmp/jaspergold-local-fpv
cp ~/.config/codex/skills/jaspergold-local-fpv/assets/stop_on_first_cex_vcd.tcl \
  private/tmp/jaspergold-local-fpv/
```

Then, inside the sourced container shell:

```sh
export FTRUN_BASE_TCL="$TB_HOME/scripts/flt.tcl"
export FPV_MAX_JOBS=2
export FPV_PROOF_LIMIT=10m
export FTRUN_RUN_LIMIT="$FPV_PROOF_LIMIT"
export FTRUN_PROVE_TASK=prj_prove_all
ftrun tex_flt \
  -tcl /gpu/private/tmp/jaspergold-local-fpv/stop_on_first_cex_vcd.tcl \
  -build_dir /gpu/private/tmp/jaspergold-local-fpv/fts_run_tex_flt \
  -local -batch -auto_run -slots "$FPV_MAX_JOBS" -save on_failure
```

In a C-shell environment, use `setenv NAME value` instead of `export`.

The wrapper applies `FTRUN_RUN_LIMIT` before the common `pre_configure` hook,
because the common hook validates proof runtime against the outer session
limit. It sets both the JG default and the selected task's prove-strategy
`run_limit` when a strategy is present.

## 5. CPU/job and time controls

These controls are related but not interchangeable.

Validate caller-supplied parameters before starting a run. `FPV_MAX_JOBS`
must be a positive integer. `FPV_PROOF_LIMIT` must be a positive Jasper/FTS
duration such as `60s`, `10m`, or `2h`. Record both values with the result.

### Proof concurrency

- `ftrun ... -slots N`: FTS maximum proof-job/slot count. FTS maps this into
  Jasper proof-grid job settings.
- `set_proofgrid_max_local_jobs N`: direct Jasper local-job cap for an
  interactive session.
- `::fts::prove ... -max_jobs N`: FTS Tcl API control for one proof request.
- `engine_threads`: threads inside an individual Jasper engine; it is not the
  number of parallel engines.

Call these "jobs" or "slots", not simply CPUs. Jasper can create more helper or
orchestration processes than the requested slot count.

### Proof duration

- `tool_config.jg.run_limit`: default active Jasper proof-step time.
- `runtime.prove_strategies.<name>.run_limit`: active time for a task using
  that strategy; this takes precedence over the tool default.
- `set_prove_time_limit 10m` or `prove -time_limit 10m`: direct Jasper limit.
- `::fts::prove -run_limit 10m`: FTS Tcl API limit.

### Whole-session duration

- `machine.time_limit`: how long the entire allocated FTS session can live,
  including elaboration, reporting, saves, inter-step delays, and run-limit
  buffer.
- FTRun CLI `-time_limit`: outer formal-tool job allocation; current
  BlkFormal documentation states that it has no effect with `-local`.

For local proof time, never rely only on `ftrun -time_limit`.

### FTS Tcl API alternative

In a custom FTS hook, the supported high-level pattern is:

```tcl
::fts::prove -props {.*} -run_limit 10m -max_jobs 6 -bg
::fts::wait_and_report -interval 1m -cex_limit 1 -cex_format vcd
```

The interval is required for periodic CEX saving; without `-interval`, the CEX
options are ignored until the final report. `-cex_limit 1` limits saved traces;
it does not by itself stop all proof work.

## 6. Stop on first CEX and export VCD

The supplied wrapper configures:

```tcl
::fts::cfg_set {runtime failure_limit} 1
::fts::cfg_set {runtime tasks prj_prove_all fail_on} cex
::fts::cfg_set {report save_cex format} vcd
::fts::cfg_set {report save_cex limit} 1
::fts::cfg_set {report save_cex source} tool
```

This asks FTS to treat the first CEX as the failure limit and preserves a raw
VCD fallback. In its final hook it finds the first enabled `cex` or `ar_cex`,
creates a violation trace, performs a synchronous QuietTrace replot, and saves
a second VCD under `jgproject/`.

The export sequence was smoke-tested with Jasper 2025.09: a one-cycle CEX was
found, the proof engines shut down, FTS wrote its raw VCD and reports, the JDB
was saved, and the custom final hook wrote the QuietTrace VCD. The smoke test
contained one failing property, so for a many-property proof treat immediate
first-failure shutdown as configured/best-effort and verify the actual session
log for `Initiating shutdown of proof`.

The tested batch QuietTrace commands are synchronous:

```tcl
visualize -violation -property $prop -window first_cex -batch -silent
visualize -replot -quiet -window first_cex -batch -silent
visualize -save -vcd $vcd_root -window first_cex -force
```

Do not add `-bg` to the batch replot unless a corresponding wait is also added;
otherwise the VCD save can race the replot.

Expected artifacts include:

- raw FTS VCD in the `fts_run_<target>/` root;
- QuietTrace VCD in `fts_run_<target>/jgproject/`;
- `fts_run_<target>/db0/jdb` from `-save on_failure`;
- proof and resource reports described below.

## 7. Restore and inspect an existing run

Prefer the GPU Formal restore helper over reconstructing the Jasper command:

```sh
gf_restore_jasper_session /path/to/fts_run_tex_flt --dry-run
gf_restore_jasper_session /path/to/fts_run_tex_flt
gf_restore_jasper_session /path/to/fts_run_tex_flt --mode console
gf_restore_jasper_session /path/to/fts_run_tex_flt --mode agent
```

The helper accepts an `fts_run_*` directory or a direct `db*/jdb` path. Use
`--workdir` only when it cannot infer the formal directory containing
`sourceme`; `--workdir` is not the run directory.

Where the installed GPU Formal version provides agent helpers, start with:

```text
jg_list_cex
jg_open_trace <property> live_trace
jg_val_in_window live_trace <signal> <cycle>
jg_prop_timeline <property> {1 2 3} {signal_a signal_b}
jg_why <signal> <cycle>
jg_fanin <signal>
jg_export_vcd
```

Use the live value/timeline/why/fanin queries first. Use `jg_export_vcd` only
when a retained waveform is required, and check its help in the installed
version because its arguments are version-dependent.

## 8. Reports and run artifacts

Start with these files in `fts_run_<target>/`:

- `args.json` and `run.cmd`: exact invocation.
- `config.json`: resolved static target configuration.
- `jgproject/jg.log`, `jgproject/jg_console.log`, and
  `jgproject/sessionLogs/session_0/jg_session_0.log`: Jasper/FTS commands,
  applied limits, proof shutdown, and errors.
- `proof_report.rpt` and `proof_report.json`: periodically refreshed proof
  status.
- `verification_results.json`: parsed/scored proof results when scoring
  succeeds.
- `<target>_results.rpt`: direct Jasper summary from the common final flow.
- `fts_ipvs_results.json`: raw IPVS data.
- `resource_usage_report.md`, `resource_usage_report.json`,
  `resource_usage.json`, and `fts_status.db`: memory, CPU, job, and restart
  evidence.
- `testcase.tcl` and `testcase_rel_paths.tcl`: commands used for replay.
- `db0/jdb`: restorable database when save policy triggered.

Runtime `cfg_set` changes made by a Tcl hook may not appear in `config.json`.
Verify them in the Jasper session log.

For manual aggregate reports after sourcing the environment:

```sh
gf_report_gen ipvs \
  --env_name fb_tex_flt \
  --run_dir /path/to/fts_run_tex_flt \
  --out_base_path /gpu/private/tmp/<task-name>/reports \
  --milestone alpha

gf_report_gen ipds \
  --env_name fb_tex_flt \
  --run_dir /path/to/fts_run_tex_flt \
  --out_base_path /gpu/private/tmp/<task-name>/reports \
  --milestone alpha
```

Expected aggregate outputs are `ipvs_report.html/.rpt` and
`ipds_report.html/.rpt`. The standard run may also produce
`ipvs_report.txt/.html` in its own build directory.

## 9. Resource and correctness pitfalls

### Licence checkout stalls

Do not call a checkout stall a licence denial unless Jasper reports a denial.
The known `fb_tex_flt` GUI path checks out `jasper_interactive` and then
`jasper_fpv`; batch requests `jasper_fpv` directly. Both paths have succeeded
with Jasper 2025.09 and `CDS_LIC_FILE=15280@cdslmd.lic.arm.com`, so that
difference alone is not a root cause.

If a fresh log remains at `checking out 'jasper_fpv'` for about 60 seconds:

1. Record the log, Jasper version, `CDS_LIC_FILE`, and running
   Jasper/FTRun/container processes.
2. Stop the stalled run cleanly and verify that no Jasper child remains.
3. Retry once in a fresh wrapper container without changing the target, Tcl,
   YAML, module, or licence variables.
4. If batch stalls again, run the exact GUI baseline from Section 3. If that
   works, report a batch checkout stall; do not rewrite the licence environment
   or restart a healthy Colima VM.

Use `lmutil` only as supporting evidence. A failed `lmstat` does not outweigh a
successful Jasper checkout from the exact target environment.

### ProofMaster and memory

`fb_tex_flt` enables Jasper orchestration. In prior local runs, six slots and
even a reduced-slot orchestration run exhausted a roughly 19.5 GiB Docker
memory limit. ProofMaster can overwrite `prove_orchestration` and fan out more
engines than expected. A warning such as `WPF073` is evidence that a direct
orchestration setting was overwritten.

For a deliberate uncached debug run, create a temporary YAML fragment under
`private/tmp/<task-name>/`, include `project_disable_prove_cache`, and append
that file to `BLKFORMAL_CONFIG` after sourcing the normal environment. Do not
edit project-wide formal configuration merely to reduce a local run:

```yaml
"tex_flt_local_debug":
  include: ['tex_flt', 'project_disable_prove_cache']
  main:
    description: "Bounded local TF-FLT debug"
  tool_config:
    jg:
      run_limit: 10m
  flow_config:
    default:
      engines:
        jg_orchestration: False
```

Then run the temporary target and inspect the log to confirm ProofMaster and
orchestration state. Disabling cache trades speed for predictable fresh proof
behavior; do it only when that is the debug goal.

After writing that fragment as
`/gpu/private/tmp/<task-name>/local_debug.yaml`, append it without replacing the
normal configuration loaded by `sourceme`:

```sh
export BLKFORMAL_CONFIG="$BLKFORMAL_CONFIG /gpu/private/tmp/<task-name>/local_debug.yaml"
ftrun tex_flt_local_debug -local -batch -auto_run -slots 2 -save on_failure
```

### Other common failures

- `Skipping auto_run`: rerun with `-auto_run` if proof was intended.
- Fast results after semantic RTL/property changes: inspect whether ProofMaster,
  proof cache, or TraceReplay supplied the result.
- `SIGKILL` or exit 137: treat as memory/infrastructure failure; lower slots,
  disable orchestration/cache through supported configuration, or increase the
  container limit.
- QuietTrace consumes too much memory: retain the raw FTS VCD and restore the
  JDB for live queries instead.
- No CEX VCD: confirm `report.save_cex.limit` is nonzero, use `source: tool`,
  and ensure `wait_and_report` had an interval or the final hook ran.
- Missing reports/JDB: confirm the custom target sourced the base Tcl and called
  the original common hooks.
- Stale SSH agent: ensure `SSH_AUTH_SOCK` is a live socket before invoking the
  Docker wrapper.
- GUI display failure: use batch/console mode when no GUI is needed; otherwise
  establish XQuartz access and revoke it after use.

## 10. Internal references

- [BlkFormal CLI](https://formal.arm.com/docs/blkformal/1.1.0/cli.html)
- [FTS Tcl API](https://formal.arm.com/docs/blkformal/1.1.0/fts_api.html)
- [FTS schema](https://formal.arm.com/docs/blkformal/1.1.0/schema.html)
- [FTS generated files](https://formal.arm.com/docs/blkformal/1.1.0/files.html)
- [GPU Formal Jasper restore](https://gpudocs.server.eu02.arm.com/gf-user-docs/version_9a6de3da03924d3c867721eba53a7679/reference/restore_jasper_session.html)
- `verification/components/gpu_formal/docs/user/source/reference/regression_limits.md`
- `verification/components/gpu_formal/fts/gf_fts_misc_jg.tcl`
- `verification/components/gpu_formal/fts/gf_fts_report_jg.tcl`
- `verification/formal/common/fts/project.yaml`
- `verification/formal/fb_tex_flt/scripts/flt.yaml`
- `verification/formal/fb_tex_flt/scripts/flt.tcl`

These are versioned interfaces. Check `ftrun -h`, the resolved config, and the
session log when the installed FTS/Jasper version differs.
