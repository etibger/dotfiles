---
name: setup-gpu-repo-rhel8
description: Create and prepare an isolated hash-named GPU worktree on rhel8-VM directly from a push_gpu candidate ref. Use before formal, simulation, lint, or other downstream work; never alter or reuse the push_gpu checkout.
---

# Set Up GPU Repo on RHEL8

Use `/home/tibger01/projects/fornjot/push_gpu` only as the Git worktree
manager. Resolve the transferred candidate ref there and create a dedicated
sibling worktree at the exact commit. Never reset, clean, or switch the
manager checkout.

## Profiles

- `fpv` creates `tmp_gpu_fpv_run_<sha12>`.
- `blk-run` requires `--regression sanity|smoke|nightly` and creates
  `tmp_gpu_blk_run_<sha12>_<regression>`.

Profiles affect only isolation and naming. Both prepare the repository through
`design/logical/make sources` and then stop; they do not source a formal,
simulation, lint, or other downstream environment.

## Create and retain

Stream [scripts/setup_worktree.sh](scripts/setup_worktree.sh) to RHEL8. For
example:

```sh
ssh -o BatchMode=yes rhel8-VM 'bash -s -- \
  --candidate-ref fpv-candidate-<sha12> --workflow fpv' \
  < ~/.config/codex/skills/setup-gpu-repo-rhel8/scripts/setup_worktree.sh
```

For simulation add `--workflow blk-run --regression sanity`. If preparation
fails after creation, retain the worktree and use `--resume-existing` only
with the same candidate ref. Read [references/worktrees.md](references/worktrees.md)
before recovery or removal.

Worktrees are retained by validation workflows whether a check passes or
fails. Remove one only on a later explicit cleanup request by streaming
[scripts/remove_worktree.sh](scripts/remove_worktree.sh) with its exact
reported path, matching profile arguments, and `--yes`.
