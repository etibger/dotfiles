---
name: setup-gpu-repo-eu3
description: Create, prepare through design source generation, and safely remove an isolated hash-named GPU repository worktree on EU3 from push_gpu's fixed eu3-candidate ref. Use before formal, simulation, lint, or other downstream work; never clean, reset, or reuse the push_gpu checkout itself.
---

# Set Up GPU Repo on EU3

Use `/arm/projectscratch/mpd/pj33000696_njord/users/tibger01/push_gpu`
only as the Git worktree manager. Never clean, reset, check out, or otherwise
modify its checkout. Create a dedicated sibling worktree and do not use lock
files.

## Candidate and workflows

- SSH target: `eu3`, using the Keychain-backed password askpass configuration
  from `$transfer-git-commit-to-eu3`.
- Candidate: the commit resolved from the fixed
  `refs/heads/eu3-candidate` ref in `push_gpu` when setup starts.
- No candidate-ref option, base ref, base hash, or caller-supplied commit is
  accepted. Dirty files in `push_gpu` are not included.
- `$transfer-git-commit-to-eu3` updates this exact fixed ref. The current
  checkout and `HEAD` of `push_gpu` are irrelevant and remain untouched.

The setup and removal scripts accept two bounded naming profiles for caller
compatibility:

- `fpv` is the default. It uses `tmp_gpu_fpv_run_<12-char-sha>`.
- `blk-run` requires `--regression sanity|smoke|nightly`. It uses
  `tmp_gpu_blk_run_<12-char-sha>_<regression>`.

Both profiles perform the same neutral repository preparation through
`design/logical/make sources`. The profile selects only worktree naming and
cleanup guards; it does not select or load a downstream tool environment.

The worktree must start at and remain on the exact fixed-ref commit resolved by
the setup script.

## Create and prepare

Obtain authorization before creating the remote worktree unless the current
request already grants it. Stream [scripts/setup_worktree.sh](scripts/setup_worktree.sh)
to EU3 with the existing Keychain askpass helper:

```sh
SSH_ASKPASS="${XDG_CONFIG_HOME:-$HOME/.config}/zshrc/ssh-askpass-keychain" \
SSH_ASKPASS_REQUIRE=force \
ssh -o BatchMode=no -o PubkeyAuthentication=no \
  -o PreferredAuthentications=password,keyboard-interactive \
  -o NumberOfPasswordPrompts=1 eu3 \
  'bash -s -- --workflow fpv' \
  < ~/.config/codex/skills/setup-gpu-repo-eu3/scripts/setup_worktree.sh
```

For `blk-run`, pass `--workflow blk-run --regression sanity|smoke|nightly`.
If creation succeeded but preparation failed, rerun the same workflow with
`--resume-existing`. The script verifies the registered path, temporary
branch, and exact current `eu3-candidate` commit before resuming; it never
adopts an arbitrary existing directory.

After component update and the strict second `design/sourceme`, the script runs
`design/logical/make sources` and stops. Do not enter or source `fb_tex_flt`,
`tb_tex`, lint, or any other downstream environment. The user or calling agent
chooses and initializes the next workflow separately.

Read [references/worktrees.md](references/worktrees.md) before recovering a
partial setup or removing a worktree.

## Cleanup

Retain a worktree while its proof database, logs, or debug state are needed.
When cleanup is authorized, stream [scripts/remove_worktree.sh](scripts/remove_worktree.sh)
with the exact reported `WORKTREE`, matching workflow arguments, and `--yes`.
The guard rejects `push_gpu`, invalid workflow-specific names, unregistered
paths, and worktrees referenced by matching active formal or simulation
processes.

For bounded pre-run cleanup, add `--if-exists`. It removes only the exact
registered worktree and temporary branch and also succeeds when neither
remains.
