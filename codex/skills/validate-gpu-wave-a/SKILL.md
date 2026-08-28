---
name: validate-gpu-wave-a
description: "Orchestrate the negative-test Wave A GPU validation gate for one committed base..tip range: serialized design source generation, then concurrent AACR, fixed-seed Mac tb_tex sanity, bounded Mac fb_tex_flt FPV, and RHEL8 TEX lint with durable normalized evidence. Use when proving that all three technical detectors independently find an intentional candidate bug before Wave B; do not use as a clean-candidate gate or for debug reruns."
---

# Validate GPU Wave A

Wave A is an intentional-bug detector test. Confirm the exact committed
`base..tip` range and supply evidence regexes that attribute each technical
failure to that bug. The lint regex is mandatory because an unrelated lint
violation must not pass the gate.

Run a non-mutating plan first:

```sh
<skill>/scripts/run_wave_a.sh \
  --repo <gpu-repo> --base <full-base-sha> --tip <full-tip-sha> \
  --simulation-pattern 'legal_hdr_return_addr' \
  --fpv-pattern 'legal_hdr_return_addr' \
  --lint-pattern '<intentional-bug-lint-signature>' \
  --dry-run
```

Then run the same command without `--dry-run`. The executor:

1. Rejects anything other than a clean tracked current-HEAD tip and an
   ancestor base.
2. Starts one transient combined Xcelium/JasperGold devcontainer.
3. Completes one synchronous `design/logical/make sources` preflight and
   publishes a candidate-bound serialization manifest. This barrier is
   mandatory: simulation and FPV must never race source generation.
4. Launches AACR `base..tip`, fixed seed-1
   `test_mix_all_tiny__sanity`, `tex_flt` FPV at 10 minutes/four slots, and
   RHEL8 Superlint concurrently. It waits for every branch and never stops
   siblings after an early finding.
5. Writes schema-v2 `orchestration.env` plus per-attempt start, finish, and
   collection markers under `orchestration/`. This evidence binds the live
   coordinator run ID, exact `base..tip`, coordinator-observed UTC chronology,
   selected run-relative summary and raw command/config paths, and raw-byte
   SHA-256 digests. The command evidence binds AACR's uncached exact range,
   seed-1 no-wave simulation, FPV target/time/four-slot/Tcl wrapper identity,
   and RHEL8 candidate/run/8x-lint identity. Gate A
   rejects schema-v1 provenance, duplicate, missing, stale, path-swapped, retry-swapped,
   nonzero selected executors, branches that did not overlap the all-started
   barrier, or chronologically inconsistent evidence.
6. Normalizes retained evidence and writes `state.json`, `summary.txt`, and
   `STATUS.md` under
   `<repo>/private/tmp/to_persist/validation-campaign/wave-a/runs/<run-id>/`.

Read the path printed as `WAVE_A_SUMMARY_JSON`. Gate A passes only when AACR
completed and simulation, FPV, and lint each have an attributable detection.
An attributable formal CEX remains a valid detector result if the formal
process later hits the known memory/infrastructure limit; the branch retains
`execution_status=INFRASTRUCTURE_ERROR` and
`classification=VALIDATION_DETECTED_WITH_INFRA_LIMIT` so that incompleteness
is never hidden.

Gate A is fail-closed for provenance. A schema-v1 parallel claim, a summary
copied from another run, or a retry that was not the attempt started before the
first completion wait cannot be promoted by adding fields retrospectively.
Missing strong evidence remains `BLOCKED` even when detector payloads would
otherwise pass.

New coordinator runs must contain collection-bound command SHA-256 fields for
all four branches. The combiner's `--allow-legacy-command-evidence` switch is
only for an explicitly selected, pre-existing schema-v2 historical run that
predates those fields; it still validates every retained raw command and marks
the weaker binding mode in `state.json`. The live coordinator never enables
that compatibility switch, so deleting command digests cannot downgrade a new
run silently.

The FPV executor saves at most five VCDs. It does not yet implement a tested
stop-after-five-individual-CEX monitor. Keep that executor gap visible rather
than claiming the requested CEX stop cap is enforced.

Do not clean the RHEL8 worktree or any large branch artifact automatically.
Cleanup remains a separate user-directed action.
