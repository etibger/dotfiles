---
name: transfer-git-commit-to-rhel8
description: Transfer one committed GPU repository candidate to a key-authenticated RHEL8 SSH host through a bare Git handoff repository. Use when a remote validation needs the exact local commit without copying a full worktree; do not use for uncommitted changes or general deployment.
---

# Transfer Git Commit to RHEL8

Transfer only the commit and missing Git objects needed by the remote host. The
default handoff is `rhel8-VM:git-transfer/c_gpu.git`, branch
`refs/heads/fpv-candidate`.

## Contract

- Require key-only access: `ssh -o BatchMode=yes rhel8-VM true` must succeed.
- Never retrieve, print, or pass a password. Do not enable agent forwarding.
- Transfer `HEAD`, not the local working tree. Stop if tracked staged or
  unstaged changes exist; untracked files are not transferred.
- The handoff branch is intentionally replaceable. Obtain authorization before
  the external `git push --force` unless the current user request already grants
  it.
- A normal Git push negotiates and sends missing objects; do not archive, rsync,
  or force-push an entire worktree.

## Procedure

Run [scripts/transfer_candidate.sh](scripts/transfer_candidate.sh) from the
candidate repository:

```sh
~/.config/codex/skills/transfer-git-commit-to-rhel8/scripts/transfer_candidate.sh \
  --repo . --host rhel8-VM --remote-ref fpv-candidate
```

Record its `CANDIDATE_SHA`, `REMOTE_REF`, and `CLOSEST_ORIGIN_REF` output. The
closest origin ref minimizes symmetric commit distance from the candidate among
origin branches that contain the candidate's nearest origin-reachable boundary
commit. This still works when the origin branch advanced after the local topic
forked. The result supplies worktree branch context; it does not replace
checking out the exact candidate.

Verify the remote ref resolves to the exact local SHA before continuing.
