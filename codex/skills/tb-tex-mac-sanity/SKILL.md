---
name: tb-tex-mac-sanity
description: Run the fixed Wave A tb_tex test_mix_all_tiny__sanity simulation in the Mac GPU devcontainer with seed 1 and no waves, retain native artifacts, and normalize pass or candidate-failure evidence. Use only after the shared design make-sources preflight; do not use for regressions or debug-wave reruns.
---

# Mac tb_tex sanity detector

This executor runs inside the `xcelium_jaspergold_blkformal` devcontainer. Use
the Wave A coordinator so design sources are generated once before simulation
and formal start concurrently. A direct invocation must provide the successful
source-preflight manifest for the exact candidate:

```sh
<skill>/scripts/run_sanity.sh \
  --repo /gpu --candidate <full-sha> \
  --source-preflight /gpu/private/tmp/to_persist/<campaign>/source-preflight.env \
  --output-dir /gpu/private/tmp/to_persist/<campaign>/simulation \
  --expected-pattern 'legal_hdr_return_addr'
```

The fixed native command is:

```sh
blk_val --build-clean --storage-services elk=n \
  --set-lsf-mem-limit 12000 --no-bsub --no-bsub-build \
  --dfs batch --bo 8x_mtcs --seed 1 \
  --plusarg "+tex_trace_shim +tex_checkers_enable=all" \
  test_mix_all_tiny__sanity
```

Do not add UVM-high output or waves to this initial detector. The executor runs
`blk_status` on the exact emitted batch log and writes `summary.json`.
It also retains `command.txt`; Gate A requires its raw bytes and normalized
fields to agree with this exact test, seed, DFS mode, build option, and no-wave
contract.
`DETECTED` means the test completed with a BLK failure whose retained evidence
matches `--expected-pattern`; an unrelated failure is `UNATTRIBUTED_TEST_FAILURE`
and cannot satisfy the negative-test gate. A setup,
compile, missing-log, skipped-test, licence, or resource failure is
`INFRASTRUCTURE_ERROR`, not bug evidence. Retain `run/`, the batch log, error
JSON, compile metadata, and summary for later replay.
