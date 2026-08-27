---
name: setup-gpu-repo-rhel8
description: Create and prepare an isolated hash-named GPU repository worktree on the rhel8-VM host from a transferred candidate. Use before remote GPU simulation, lint, or formal validation; do not clean or reuse shared a_gpu, b_gpu, tmp_gpu, or tmp2_gpu worktrees.
---

# Set Up GPU Repo on RHEL8

Use `/home/tibger01/projects/fornjot/a_gpu` only as the Git worktree manager.
Never clean or modify its checkout. Create a dedicated sibling worktree for the
exact candidate and do not use lock files.

## Inputs and output

- SSH target: `rhel8-VM`.
- Handoff ref: `refs/heads/fpv-candidate` in
  `/home/tibger01/git-transfer/c_gpu.git`.
- Optional base: the `CLOSEST_ORIGIN_REF` reported by
  `$transfer-git-commit-to-rhel8`.
- Worktree: `/home/tibger01/projects/fornjot/tmp_gpu_fpv_run_<12-char-sha>`.
- Temporary branch: `tmp_fpv_run_<12-char-sha>`.

The base origin ref supplies branch context, but the new worktree must be reset
to and verified against the exact candidate SHA.

## Create and prepare

Stream [scripts/setup_worktree.sh](scripts/setup_worktree.sh) to the host. Pass
the closest origin ref when it is known:

```sh
ssh -o BatchMode=yes rhel8-VM 'bash -s -- \
  --candidate-ref fpv-candidate \
  --base-ref origin/ctt/tex/fornjot_main' \
  < ~/.config/codex/skills/setup-gpu-repo-rhel8/scripts/setup_worktree.sh
```

If worktree creation succeeded but component/source preparation failed, rerun
the same command with `--resume-existing`. The script verifies the registered
path, temporary branch, and exact candidate SHA before resuming; it never
adopts an arbitrary existing directory.

The script fetches only the handoff candidate, creates the isolated worktree,
then runs the required setup sequence:

```sh
cd design
source ./sourceme
git components update --force
cd logical
make sources
cd ../../verification/formal/fb_tex_flt
source ./sourceme
```

Read [references/worktrees.md](references/worktrees.md) before choosing a base,
recovering a partial setup, or removing a worktree.

## Cleanup

Retain the worktree when the user needs the proof database or further debug.
When cleanup is authorized, run `scripts/remove_worktree.sh` remotely with the
exact reported worktree and `--yes`. The guard rejects shared repositories,
non-hash names, and a worktree containing an active Jasper/FTRun process.
