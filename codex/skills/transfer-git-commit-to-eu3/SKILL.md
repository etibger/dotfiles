---
name: transfer-git-commit-to-eu3
description: Transfer one committed GPU repository candidate to the password-authenticated EU3 HPC host through a fixed Git handoff repository. Use when remote EU3 work needs the exact local commit without copying a worktree; do not use for uncommitted changes, arbitrary destinations, or general deployment.
---

# Transfer Git Commit to EU3

Transfer only the commit and missing Git objects needed by EU3. The fixed
handoff is
`eu3:/arm/projectscratch/mpd/pj33000696_njord/users/tibger01/push_gpu/`,
branch `refs/heads/eu3-candidate`.

## Prerequisites

- The `eu3` SSH alias must resolve to `tibger01@login43.hpc01.eu03.arm.com`
  and enable password or keyboard-interactive authentication without agent
  forwarding. Never put the password in `~/.ssh/config`.
- Authentication uses the executable
  `~/.config/zshrc/ssh-askpass-keychain`, which reads account `tibger01` and
  service `com.arm.ssh.tibger01` from macOS Keychain only when OpenSSH asks for
  a password. Do not call Keychain with `-w` from the agent or capture its
  output.
- Review and establish host-key trust interactively before the first automated
  transfer, then validate Keychain-backed login with `arm-ssh eu3 true`. Do
  not disable strict host-key checking.
- Before a live transfer, confirm that the fixed destination has been
  initialized as the intended handoff repository and permits updates to the
  candidate branch. Installing or dry running this skill does not probe or
  modify it.

## Contract

- Transfer `HEAD`, not the working tree. Stop if tracked staged or unstaged
  changes exist; untracked files are not transferred.
- Keep the host and remote repository fixed. The handoff branch is
  intentionally replaceable; obtain authorization before the external
  `git push --force` unless the current user request already grants it.
- Pass only the askpass helper path to SSH. Never print, store, interpolate, or
  pass the password in a command, URL, argument, or ordinary environment
  variable. Do not use `sshpass`.
- Do not use `BatchMode=yes`: this host intentionally uses password-backed
  askpass. The helper refuses host-key and other unexpected prompts.
- Use normal Git object negotiation; do not archive, rsync, or force-push a
  full worktree.
- Verify the transferred ref with `git -C <handoff-repository>` so verification
  works for either a normal or bare Git repository.

## Procedure

Run [scripts/transfer_candidate.sh](scripts/transfer_candidate.sh) from the
candidate repository:

```sh
/Users/tibger01/.config/codex/skills/transfer-git-commit-to-eu3/scripts/transfer_candidate.sh \
  --repo . --remote-ref eu3-candidate
```

Do not prefix the installed script with `bash`, `zsh`, `env`, or another
launcher. Use `--dry-run` while the destination is not ready; it performs only
local Git validation and does not invoke SSH or push.

Record `CANDIDATE_SHA`, `REMOTE_REF`, and `CLOSEST_ORIGIN_REF`. The closest
origin ref supplies downstream branch context but never replaces checking out
the exact candidate. After a live transfer, require `REMOTE_VERIFIED=1` before
continuing.
