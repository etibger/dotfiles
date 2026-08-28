---
name: transfer-git-commit-to-rhel8
description: Transfer one committed GPU candidate to key-authenticated rhel8-VM through the fixed push_gpu Git handoff repository. Use when RHEL8 validation needs the exact local commit; do not use for uncommitted worktrees or general deployment.
---

# Transfer Git Commit to RHEL8

Transfer only the commit and missing Git objects needed by RHEL8. The fixed
handoff repository is `/home/tibger01/projects/fornjot/push_gpu`; candidate
refs may be replaced without moving or cleaning that repository's checkout.

## Contract

- Require key-only access: `ssh -o BatchMode=yes rhel8-VM true` must succeed.
- Transfer current committed `HEAD`, not working-tree content. Reject tracked
  staged or unstaged changes; untracked files are not transferred.
- Never reset, clean, switch, or otherwise change the `push_gpu` checkout.
- Obtain authorization before the external force-update unless the current
  request already authorizes candidate transfer.
- Use a normal Git push, then verify the exact commit with
  `git -C /home/tibger01/projects/fornjot/push_gpu rev-parse`.

## Procedure

Run [scripts/transfer_candidate.sh](scripts/transfer_candidate.sh) from the
candidate repository:

```sh
~/.config/codex/skills/transfer-git-commit-to-rhel8/scripts/transfer_candidate.sh \
  --repo . --host rhel8-VM --remote-ref rhel8-candidate
```

Use SHA-specific refs for concurrent workflows, for example
`fpv-candidate-<sha12>` and `blk-run-candidate-<sha12>`. Record
`CANDIDATE_SHA`, `REMOTE_REF`, and `REMOTE_VERIFIED`; require the verified
remote SHA to match before setting up a worktree. `--dry-run` performs only
local validation.
