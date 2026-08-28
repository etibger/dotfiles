# Remote fb_tex_flt workflow

## Sequence

1. Verify the candidate equals current local `HEAD` and the tracked tree is
   clean.
2. Transfer it to a SHA-specific FPV ref in RHEL8 `push_gpu` without touching
   the manager checkout.
3. Create and prepare `tmp_gpu_fpv_run_<sha12>` through `make sources`.
4. Stage `capture_up_to_five_cex_vcd.tcl`, `run_fpv.sh`, the process sampler,
   `disable_campaign_prove_cache.yaml`, and the summary tool under the worktree's task-specific
   `private/tmp/to_persist` directory.
5. Source `fb_tex_flt/sourceme` once and run `ftrun tex_flt -local -batch
   -auto_run -slots <jobs>` with the requested active limit. For a campaign
   sanity attempt, pass `--campaign-no-prove-cache`; the exact launch becomes
   `ftrun tex_flt -include validation_campaign_disable_prove_cache -tcl
   <wrapper> -local -batch -auto_run -slots <jobs> -save on_failure`, and the
   runner records it in `ftrun-invocation.rpt`. The Tcl wrapper
   records the same limit in the active prove strategy and applies Jasper's
   `set_proofgrid_per_engine_max_local_jobs` and
   `set_proofgrid_max_local_jobs` controls after normal configuration but
   before `auto_run`.
6. Generate aggregate assertion/cover reports with task-local Python 3.12,
   verify the wrapper marker, effective IPF031 local cap, and bounded
   ProofGrid usable levels; collect small reports and replay metadata; and
   retain the worktree.

The raw CEX-save limit is five. The five-minute active proof limit is the
verified hard stop. Do not set or describe FTS `runtime.failure_limit=5` as an
individual-property cap: `prj_prove_all` is one task, and a live cached-CEX run
demonstrated that this setting did not stop after five property failures. A
tested property-count monitor remains a deliberate executor gap.

## Concurrency evidence

Do not infer the local proof-job cap from `-slots` or `config.json` alone.
ProofMaster can replace generic `set_proofgrid_max_jobs` settings with `auto`.
The normalized result is eligible to pass only when its `concurrency` object
is `VERIFIED`: the run log must contain the wrapper's requested local-cap
marker, every subsequent IPF031 local proof-thread block must remain bounded
at or below the requested jobs, and at least one must report the exact
requested total plus `max engine jobs = ... (max <jobs>)`. The summary tool
writes diagnostic evidence and returns status 2 when this contract is not
met; the runner propagates it. During FTRun, the runner also samples only
`jg_proof` processes whose command line contains this run's proof directory.
It retains raw epoch/count data in `proof-process-samples.rpt` and, for new
runs, PID, PPID, state, CPU, elapsed time, `comm`, role, and argv in
`proof-process-details.tsv`. Linux `comm` identifies the real Jasper engine
executable; `jg_proof` is the first `args` field. `comm=jg_engineCache`
identifies a ProofMaster prove-cache worker even though its argv contains a
`.proofgrid_*.bs` command file. Other `.proofgrid_*.bs` rows are ordinary
proof engines; remaining matched argv is controller/other.

The authoritative cap combines the wrapper marker, post-marker IPF031 caps,
ProofGrid usable level, and the ordinary proof-engine peak. Each must stay at
or below the request. Prove-cache and controller/helper peaks plus the raw
total CPU-worker peak are separate diagnostics and cannot alone cause a
proof-slot error. Legacy count-only evidence still fails closed except for one
isolated job-plus-one sample bracketed by bounded samples and correlated with
a logged retiring/replacement engine turnover.

For a deterministic retry after any nonzero runner status, retain the failed
attempt and create a new isolated attempt using `--campaign-no-prove-cache`.
Its fixed fragment sets `tool_config.jg.proofmaster.enable=false` and
`tool_config.jg.prove_cache.load=false/save=false`. Never retroactively turn
the old branch into a pass merely because the updated parser distinguishes its
cache workers.

## Result semantics

A time-bounded campaign is clean when it finds no assertion CEX/error and the
tool completes normally. Unresolved properties are reported as proof
completeness rather than converted into validation failures. Full proof is
stronger evidence, but is not required for this five-minute sanity stage. A
report where every assertion is still `unprocessed` is an execution error, not
clean evidence.

## Artifact and recovery policy

Reports and small JSON/replay files are collected locally. JDBs, VCDs, and
other large generated stores remain in the retained RHEL8 worktree unless the
user requests transfer for debug. A missing summary is an orchestration error,
not a passing proof. Retry or cleanup only after inspecting the exact retained
path; never adopt a shared checkout.
