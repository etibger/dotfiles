---
name: jaspergold-mac-fpv
description: Run the fixed Wave A ten-minute, four-slot fb_tex_flt JasperGold detector on the Mac devcontainer after serialized source generation, retain proof evidence, and preserve an attributable CEX even when a later resource failure interrupts finalization. Use for negative-test Wave A only; do not claim a tested stop-after-five-CEX mechanism.
---

# Mac Wave A JasperGold FPV

Use the Wave A coordinator. It first runs `scripts/preflight_sources.sh` to
complete `design/logical/make sources` and writes a candidate-matched barrier.
Simulation and formal must not start before this barrier: a live attempt that
let FTRun lock its source snapshot while concurrent source generation was still
running was invalid and had to be restarted.

The formal executor runs inside the `xcelium_jaspergold_blkformal` devcontainer:

```sh
<skill>/scripts/run_fpv.sh \
  --repo /gpu --candidate <full-sha> \
  --source-preflight /gpu/private/tmp/to_persist/<campaign>/source-preflight.env \
  --output-dir /gpu/private/tmp/to_persist/<campaign>/fpv \
  --expected-property 'legal_hdr_return_addr'
```

It sources the normal `fb_tex_flt` environment and runs target `tex_flt` with
an active proof limit of `10m`, `-local -batch -auto_run -slots 4`, and
`-save on_failure`. Four is the FTS proof-job ceiling, not a physical CPU count.
The raw `command.txt` records the target, proof limit, four slots, per-run build
directory, and `save_up_to_five_cex.tcl` wrapper identity. Gate A validates
that artifact as well as the normalized fields.

## Five-CEX boundary and known gap

The Tcl wrapper sets `report.save_cex.limit=5`, which bounds automatically
saved raw traces when normal reporting/finalization runs. It does **not** set
`runtime.failure_limit=5`: live evidence proved that value is not an
individual-property CEX counter for this single FTS task. There is currently no
tested property-count monitor plus cancellation mechanism, so stop-after-five
CEX remains an explicit executor gap.

Read `summary.json`, not FTRun exit alone. An attributable IPF055
counterexample is `DETECTED`. If the proof then hits OOM, `broken_piped`, or
misses its final report/VCD, the summary preserves that detection as
`VALIDATION_DETECTED_WITH_INFRA_LIMIT` while setting execution to
`INFRASTRUCTURE_ERROR`. Wave A's negative-test gate may accept that conclusive
detection, but the incomplete execution must remain prominent. Never describe
it as a clean or complete proof.
