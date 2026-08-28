---
name: aacr-range-review
description: Run AACR deep Codex analysis over an explicit committed Git base..tip range, retain machine-readable and human-readable evidence, and classify whether the range produced a review finding. Use for the Wave A review detector; do not use uncommitted files or treat process exit alone as a candidate verdict.
---

# AACR range review

Run the fixed helper against an explicit resolved candidate range:

```sh
/Users/tibger01/.config/codex/skills/aacr-range-review/scripts/run_aacr_range.sh \
  --repo /Users/tibger01/Projects/Fornjot/a_gpu \
  --base <base-sha> --tip <tip-sha> \
  --output-dir <repo>/private/tmp/to_persist/<campaign>/wave-a/aacr
```

The helper requires `base` to be an ancestor of `tip`. It invokes
`aacr-cli --target-sha <base>..<tip> --deep-analysis-codex --no-caching` and
requests raw JSON, text, HTML, and a complete command log. Disabling the local
result cache makes the live branch evidence correspond to this coordinator
attempt. Internal service or network failure is `INFRASTRUCTURE_ERROR`, not a
clean review.

Read `summary.json` for the result. `detection_status=DETECTED` means AACR
reported at least one finding in the exact range. `NOT_DETECTED` means a
completed review reported zero findings. Preserve the run URL and all evidence;
the repository `.aacr/cache.litedb` is only a cache.

The Wave A mutation gate requires this review to complete and records findings
when present; the three technical mutation detectors are simulation, FPV, and
lint. A completed zero-finding AACR review therefore does not by itself block
Gate A. The coordinator validates the retained raw `command.txt`, including
the exact uncached `base..tip` range and output paths, instead of trusting the
summary's command string alone.
