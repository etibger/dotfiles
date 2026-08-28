---
name: validate-gpu-wave-b-rhel8
description: Run and gate Wave B of the GPU validation campaign on rhel8-VM, with tb_tex sanity and bounded fb_tex_flt executing concurrently against one committed candidate. Use only after Wave A passed; do not advance to EU3 when either branch is unclean.
---

# Validate GPU Wave B on RHEL8

Wave B is one explicit campaign gate with two independent branches:

- tb_tex `blk_run --sanity`, local workers, `--max-jobs 2`, regression-default
  max-fail, and the fixed 12000 MB/no-bsub options;
- fb_tex_flt `tex_flt`, 6 slots, a verified 5-minute hard stop, and at most 5
  saved CEX traces. A true stop-after-five-property-CEX mechanism is still an
  explicit executor gap.

Both branches use the same current committed candidate, transfer through
RHEL8 `push_gpu`, start concurrently, run to completion, collect every
available small result, and retain their isolated worktrees.

## Entrypoint

After recording a successful Wave A gate, use
[scripts/run_wave_b.sh](scripts/run_wave_b.sh) for local dry-run validation of
the generic branch plan:

```sh
~/.config/codex/skills/validate-gpu-wave-b-rhel8/scripts/run_wave_b.sh \
  --commit <current-HEAD-sha> --dry-run
```

For the candidate-specific final driver, retain and collect its complete
`final-result-<run-token>` directory. Also collect that exact run's remote
`final-driver-<run-token>/payload/` directory as `driver-payload/` immediately
under the local evidence root; `payload.sha256` must match it. Then invoke the
gate directly with the explicit candidate, attempt token, run token, collected
evidence root, branch statuses, and normalized summaries:

```sh
python3 scripts/gate_wave_b.py \
  --candidate-sha <exact-40-hex-candidate> \
  --attempt-token <worktree-attempt-token> \
  --run-token <final-driver-run-token> \
  --evidence-root <collected-final-result-directory> \
  --simulation-status 0 --fpv-status 0 \
  --json-output <wave-b-summary.json> \
  --text-output <wave-b-summary.rpt>
```

`--simulation-summary` and `--fpv-summary` are optional drift cross-checks;
the Gate never depends on them for PASS because it recomputes both summaries
from the validated archives.

## Gate

Wave B passes only when both normalized branch classifications are `PASS`,
both statuses are zero, and both summaries name the exact candidate. Supplied
summaries are only cross-checks: the gate materializes the two SHA-bound
archives under a retained `gate-derived/` directory and recomputes both
normalizations from the exact run members. The gate also reads—not
reconstructs—the final driver's `orchestration.env`, both
`preparation/*.env` files, and both `results/*/branch.env` files. It binds the
raw evidence to the exact candidate/attempt/run identities, proves serial
preparation and both launches before the first wait, requires collect-all,
checks exact worktree/run/task paths, command records, the archived actual FPV
`run.cmd`, the runner's `ftrun-invocation.rpt`, and the effective FTRun
`config.json`. It also requires the run log's unique `prj_prove_all` 5-minute
limit, calculated `00h 05m 00s` total, and post-wrapper effective
`time_limit=300s` settings. It verifies the payload and archive SHA-256s and requires the
exact run-bound logs/databases/proof reports. Missing, duplicate, unexpected,
contradictory, symlink-escaped, or digest-tampered evidence fails closed.
The two evidence-emitting final-driver scripts are also checked against fixed
trusted SHA-256 fingerprints; recomputing an untrusted payload manifest is not
sufficient.

Formal PASS additionally requires the wrapper marker, effective local IPF031
cap of six, ProofGrid usable levels no greater than six, and schema-v2 process
details proving the ordinary proof-engine peak is no greater than six. The
exact included campaign config must resolve `proofmaster.enable`,
`prove_cache.load`, `prove_cache.save`, and `local_prove_cache_engines` to
false in `config.json`. `comm=jg_engineCache` workers and controller/other
Jasper processes are reported separately; their raw-total peak is diagnostic
and does not redefine FTRun's proof-slot contract. Because this campaign
mandates disabled ProofMaster/prove-cache settings, Gate B nevertheless
requires the observed `jg_engineCache` peak to be zero; any such active worker
contradicts the deterministic six-engine campaign contract. Count-only legacy
turnover evidence cannot pass this gate. Canonical roles are independently derived from Linux `comm`
and the raw `.proofgrid_*.bs` argv, then cross-checked against the recorded
role. Unresolved formal properties at the five-minute limit are
recorded as incomplete proof coverage but do not fail a no-CEX sanity check.

Simulation PASS additionally requires the collected read-only
`sim2/logs_tests/cache.sqlite` ledger. Gate B independently checks its exact
six-field test-record schema, deterministic name/seed order, unique replay
identities, retained-worktree log paths, and original `blk_val` commands. It
recomputes PASS/FAIL/ABORT/SKIP counts and requires agreement with both
`regression.json` and terminal `SIMU-RES`; a summary's own `verified` flag is
not trusted by itself.

The simulation side currently binds the exact `--max-jobs 2` command and all
terminal test records, but does not attest the observed whole-run `xmsim`
worker peak. Treat runtime simulation concurrency as an explicit executor
evidence gap; a late process sample or a UI `RUNNING` counter is not a
whole-run proof.

Every combined summary translates the validated raw fields into the stable
top-level `orchestration` contract: parallel launch, both branches launched
before the first wait, all branches collected, ordered
`started_branches`/`collected_branches` lists of `[simulation, fpv]`, and the
attempt token. `orchestration_evidence` records the raw env-file SHA-256s,
archive and payload SHA-256s, recomputed-summary provenance, run token,
evidence root, and observed lifecycle timestamps. The gate never emits a
passing orchestration claim without that raw bundle.

On failure, report every captured simulation test/seed/signature, EAP triage
URL, formal failure/CEX count, local artifact path, and retained remote
worktree. Do not start Wave C. Do not auto-clean or silently retry either
branch.

Read [references/wave-b-contract.md](references/wave-b-contract.md) when
interpreting a failed gate or planning explicit cleanup.
