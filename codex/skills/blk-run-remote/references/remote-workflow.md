# Remote tb_tex blk_run workflow

## Sequence

1. Verify the requested commit is current local `HEAD` and the tracked tree is
   clean.
2. Force-update a SHA-specific candidate ref in RHEL8 `push_gpu`; do not move
   that repository's checkout.
3. Create and prepare `tmp_gpu_blk_run_<sha12>_<regression>` through
   `make sources`.
4. In one shell source `verification/tb_deploy/tb_tex/sourceme` once, create
   `sim2`, run `blk_setup`, then run the fixed local-worker command.
5. Collect the console, small text/JSON/XML results, and
   `sim2/logs_tests/cache.sqlite`. Leave waves, build stores, and other large
   artifacts remote.
6. Create `simulation-summary.json` and `.rpt`, then retain the worktree.

Simulation and FPV worktrees have different names and may run concurrently.
Two runs of the same candidate and regression intentionally collide; the
second stops instead of deleting or reusing the first.

## Interpretation

The normalized result records branch, candidate, host, command/status,
classification, failure count, every test's replay identity, failure
signatures, EAP triage URLs, and remote worktree. It takes final counts from
the canonical `sim2/regression.json`, cross-checks the last terminal
`SIMU-RES`, and opens `logs_tests/cache.sqlite` read-only with Python's standard
`sqlite3` module. The `tests` array is sorted by stored test name, seed, and
database ID and contains `name`, integer `seed`, upper-case `status`,
`substatus`, `remote_base_file`, and the exact stored `replay_command`. A PASS
requires the SQLite record count and PASS/FAIL/ABORT/SKIP counts to agree with
both aggregate sources. Missing, unreadable, malformed, or inconsistent SQLite
evidence therefore classifies as `ERROR` rather than silently accepting an
aggregate PASS.

Failure detail remains additive: `logs_tests/*_error.json` supplies the primary
signature, severity, category, and EAP link, and the matching SQLite row adds
its status, substatus, remote base file, and replay command. Threshold prose
such as `FAIL >= 200` and progress lines such as `0 FAIL` are not failure
records. Treat missing identity fields as incomplete evidence, not permission
to invent values or synthesize a replay command.

## Recovery

When setup or execution fails, retain the exact worktree and local
orchestration logs. Inspect only processes and artifacts for that path. If
large waveform or database evidence is needed, copy it in a later explicit
debug step. Cleanup is separate and must use the guarded removal helper with
the exact worktree, workflow, and regression.
