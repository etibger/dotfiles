---
name: rhel8-lint
description: Transfer the exact committed GPU candidate to the RHEL8 push_gpu handoff, prepare a retained isolated worktree, and run TEX Superlint. Use for Wave A RHEL8 lint validation; do not use for simulation, formal, shared-checkout execution, or cleanup.
---

# RHEL8 TEX lint

Run the fixed wrapper for a committed candidate. It transfers the current
`a_gpu` `HEAD` to a SHA-specific custom ref in
`/home/tibger01/projects/fornjot/push_gpu`, leaving that repository's checkout
untouched. It then creates a detached sibling worktree named from the candidate
SHA, prepares it only through `design/logical/make sources`, sources
`design/sourceme` in the downstream lint stage, and runs:

```sh
dcs_superlint superlint_8x/configuration_top.yaml
```

## Entrypoint

After installation, invoke the wrapper directly:

```sh
/Users/tibger01/.config/codex/skills/rhel8-lint/scripts/run_remote_lint.sh \
  --repo <selected-a_gpu-worktree> --commit <current-HEAD-sha> \
  --attempt-token <campaign-run-id>
```

Use `--dry-run` first to validate the committed candidate and print the fixed
host, ref, worktree, preparation boundary, lint command, retention policy, and
artifact root without SSH or remote mutation.

The live wrapper requires key-only noninteractive access to `rhel8-VM`. It
streams transfer, setup, and lint output; collects the task metadata and logs
under
`<repo>/private/tmp/to_persist/validation-campaign/wave-a/rhel8-lint/<run-id>/`;
and prints structured status fields. It also collects the small machine-readable
files `arm_lint_db/flow/{eda.log,summary.yaml,results.yaml}` and
`arm_lint_db/eda/{report.xml,report.waiver.xml}` when emitted. The large run
database remains in the retained worktree. A nonzero lint process status is
evidence to inspect, not an infrastructure success. Require the expected
`report.xml` before classifying the validation result; do not infer it from a
console footer.

Gate A hashes the raw retained driver log and validates its candidate ref,
attempt token, derived worktree, completed driver identity, and exact
`dcs_superlint superlint_8x/configuration_top.yaml` line. A summary command
field alone is not execution evidence.

## Safety and retention

- The selected repository must share the primary `a_gpu` Git common directory.
  This permits an isolated retained replay worktree but rejects an unrelated
  repository. The candidate must resolve exactly to that worktree's committed
  `HEAD`; tracked staged or unstaged changes are rejected.
- Transfer updates only
  `refs/codex/validation-campaign/rhel8-lint/<full-sha>` and verifies that the
  handoff checkout's `HEAD` did not change.
- The remote runner accepts only the fixed repository and derived
  `/home/tibger01/projects/fornjot/tmp_gpu_lint_run_<12-char-sha>_<attempt-token>`
  path. The optional token is generated when this skill runs standalone; the
  Wave A coordinator passes its run ID. This keeps repeated retained runs of
  the same commit isolated.
- An existing path or registered worktree is reported as blocked. It is never
  cleaned, reset, reused, or removed.
- Every created worktree is retained after pass, lint failure, setup failure,
  collection failure, or interruption. Cleanup is outside this skill and must
  be separately requested.

Request authorization immediately before the live transfer unless the current
user request already authorizes that campaign action. Keep the wrapper in the
foreground and report progress while it runs.
