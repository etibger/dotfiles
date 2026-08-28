---
name: jaspergold-rhel8-fpv
description: Run bounded GPU Formal fb_tex_flt on rhel8-VM from a committed candidate, retaining the isolated worktree and producing normalized proof results. Use for remote JasperGold FPV; do not use for simulation-only work or shared checkouts.
---

# JasperGold RHEL8 FPV

Use [scripts/run_remote_fpv.sh](scripts/run_remote_fpv.sh) for the controlled
workflow: transfer current committed `HEAD` through RHEL8 `push_gpu`, create an
isolated worktree, prepare through `make sources`, run `tex_flt`, collect small
reports, and retain the remote proof worktree and database.

## Defaults and bounds

- Host: key-authenticated `rhel8-VM`.
- Formal environment: `verification/formal/fb_tex_flt`.
- Target: `tex_flt`.
- Default concurrency: a verified cap of 6 local Jasper proof jobs, backed by
  6 FTRun slots.
- Default active proof time: 30 minutes; accept 1 minute through 24 hours.
- Verified stop condition: requested proof time.
- Saved-trace cap: 5 CEXs. A tested individual-property stop-after-five
  mechanism is still an executor gap; FTS `runtime.failure_limit` counts tasks
  and must not be represented as that cap.
- Local artifacts:
  `<repo>/private/tmp/to_persist/jaspergold-rhel8-fpv/<run-id>/`.

The capture wrapper preserves ordinary target Tcl hooks, applies both the FTS
strategy limits and Jasper's local ProofGrid limits immediately before
`auto_run`, saves up to five raw CEX traces, and attempts one QuietTrace for
first-pass debug. "Six processes" is normalized as six concurrent local proof
job slots, which is the limit exposed by FTS/Jasper. For validation-campaign
sanity runs, `--campaign-no-prove-cache` adds the fixed
`validation_campaign_disable_prove_cache` fragment. It disables ProofMaster
and both prove-cache load and save so the bounded run does not spend CPU on
cache-signature workers or inherit cached proof results.

## Entrypoint and result

```sh
~/.config/codex/skills/jaspergold-rhel8-fpv/scripts/run_remote_fpv.sh \
  --commit <current-HEAD-sha> --jobs 6 --proof-limit 5m \
  --campaign-no-prove-cache
```

Invoke the installed path directly. `--dry-run` performs only local
validation. A live run remains in the foreground and produces
`fpv_property_summary.json` plus `.rpt`. The normalized classification is:

- `PASS` when the bounded run has no assertion CEX/error, the six-job local
  cap is verified from the wrapper marker, effective IPF031 settings, and
  observed ProofGrid usable levels and ordinary proof-engine peak no greater
  than six; at least one
  run-scoped `jg_proof` process sample and some processed properties are also
  required, even if some properties remain unresolved;
- `FAIL` when assertion CEX/error counts are nonzero;
- `ERROR` when FTRun itself fails without an assertion failure result, or every
  assertion remains `unprocessed` so the proof did not produce validation
  evidence.

Report the separate proof-completeness, execution-evidence, and structured
`concurrency` fields, counts, proof limit, CEX save cap, and retained
worktree. New process-detail evidence classifies `comm=jg_engineCache` as a
prove-cache worker before considering its ProofGrid-shaped argv. Those workers
and controller/helpers are reported separately and do not consume ordinary
proof-job slots. The raw total CPU-worker peak remains diagnostic; an ordinary
proof-engine peak above six is an `ERROR`. Legacy count-only evidence retains
the conservative job-plus-one/turnover checks. A prior nonzero runner remains
a failed attempt even if later parsing explains its raw process peak; retain
it and start a fresh cache-disabled attempt instead of rewriting its status.
Large JDBs and VCDs stay remote by default; use
`collect_artifacts.sh --include-vcd` only when a later debug step needs traces.
No cleanup is automatic.

Read [references/remote-workflow.md](references/remote-workflow.md) before
recovery or manual artifact collection.
