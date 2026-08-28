# Wave B contract

## Fixed branch commands

Simulation:

```sh
blk_run --build-clean --sanity --set-lsf-mem-limit 12000 \
  --no-bsub --no-bsub-build --worker=local --max-jobs 2
```

Formal executes `ftrun tex_flt -include
validation_campaign_disable_prove_cache -tcl <bounded-wrapper> -local -batch
-auto_run -slots 6 -save on_failure` with an active `5m` hard run limit and a
save limit of five CEX traces. The fixed include sets
`tool_config.jg.proofmaster.enable=false` and
`tool_config.jg.prove_cache.load/save=false`. FTS
`runtime.failure_limit` counts failed tasks and is not a five-property stop;
the latter remains unverified and must be reported as an executor gap.

## Gate semantics

The branches are launched before either is awaited. The coordinator always
waits for and collects both; one early failure never cancels the other. Gate
evaluation happens only after both wrappers return and the complete final
driver evidence directory has been collected. Collect the exact remote driver
payload as `<local-evidence-root>/driver-payload/`; the result's
`payload.sha256` binds all nine files, including the attempt-aware worktree
setup script and cache-disable YAML.

The combined JSON records this as an exact top-level object:

```json
{
  "orchestration": {
    "branch_launch_mode": "parallel",
    "start_all_before_wait": true,
    "collect_all_branches": true,
    "started_branches": ["simulation", "fpv"],
    "collected_branches": ["simulation", "fpv"],
    "attempt_token": "<exact-worktree-attempt-token>"
  }
}
```

These values are translated from the raw `orchestration.env`; they are not
created from the gate's intended execution plan. The combined result also
contains `orchestration_evidence` with the exact run token and SHA-256s of all
raw env, archive, and payload evidence. Both branch summaries are recomputed
from required members of those archives; supplied summaries are cross-checks.

`PASS` requires:

- exact candidate agreement across coordinator and both summaries;
- exact explicit attempt and run tokens;
- serial, zero-status simulation-then-FPV preparation timestamps;
- both branch launch timestamps before the first wait and collect-all status;
- exact candidate-specific worktree, run ID, task directory, and command
  identities in both coordinator and branch evidence;
- zero wrapper, branch runner, and artifact archive status for simulation and
  FPV;
- an intact SHA-256-bound small-artifact archive and matching sorted file list
  for each branch;
- the exact run-token simulation ownership marker, metadata, exit status, run
  log, regression result, and SQLite ledger;
- the exact FPV run log, process samples/details, proof report, remote summary,
  recorded `ftrun-invocation.rpt`, actual `run.cmd`, and effective
  `config.json`, including the fixed include, bounded Tcl wrapper, and
  `-save on_failure`;
- run-log evidence uniquely identifying `prj_prove_all` with a 5-minute
  limit, a calculated `00h 05m 00s` highest/total bound, and every observed
  post-wrapper effective `time_limit` equal to 300 seconds;
- all remote payload hashes and collected payload contents, with reusable
  runner/Tcl/parser files equal to their staged executables and both
  evidence-emitting final-driver scripts equal to the gate's trusted SHA-256
  fingerprints;
- simulation command status zero and no normalized failure;
- a nonempty, verified SQLite test ledger whose exact records are uniquely and
  deterministically ordered, preserve each test name/integer seed/status/
  substatus/remote log/original replay command, stay under the retained
  worktree, and independently reproduce all aggregate result counts;
- formal tool status zero and no assertion CEX/error;
- native local cap marker 6/2, post-marker IPF031 proof-job caps no greater
  than six with an effective main cap of six, and no ProofGrid usable level
  above six;
- effective `config.json` values proving ProofMaster, prove-cache load/save,
  and local prove-cache engines are disabled;
- positive schema-v2 process evidence whose ordinary proof-engine peak is no
  greater than six. FTRun's local `-slots` contract applies to proof-engine
  jobs, not total Jasper OS processes. `comm=jg_engineCache` and
  controller/other peaks remain separate raw-CPU diagnostics and may raise the
  raw total without changing the meaning of `-slots`. Under this campaign's
  mandatory cache-disabled effective config, however, the observed
  `jg_engineCache` peak must be zero; nonzero cache workers fail Gate B rather
  than being blessed as overhead. Count-only legacy evidence is insufficient
  for Gate B. The normalizer derives cache/ordinary/helper roles
  independently from `comm` and raw argv and rejects contradictory recorded
  role labels.

The FPV report preserves unresolved counts separately because a five-minute
sanity run is time-bounded rather than a demand to prove every property.

The simulation branch currently proves the exact `--max-jobs 2` command and
terminal result ledger, not the observed whole-run `xmsim` peak. Closing that
executor gap requires timestamped sampling from launch through completion,
run/worktree-scoped process classification, a summary field for observed peak,
and a Gate B requirement of at most two. A late ad-hoc sample cannot establish
the whole-run maximum.

## Retention and handoff

The combined local campaign report points to each skill's artifact directory
and exact remote worktree. Worktrees and large databases/waves remain on
RHEL8, pass or fail. Cleanup is a later explicit operation. Wave C may start
only from a `PASS` Wave B summary for the same candidate.
