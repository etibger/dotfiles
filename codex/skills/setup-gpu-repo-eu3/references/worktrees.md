# EU3 GPU worktree rules

## Candidate selection

The only candidate source is the fixed transfer ref:

```sh
git -C /arm/projectscratch/mpd/pj33000696_njord/users/tibger01/push_gpu \
  rev-parse --verify 'refs/heads/eu3-candidate^{commit}'
```

Do not accept a candidate-ref option, base ref, base hash, or caller-provided
SHA. The script resolves `refs/heads/eu3-candidate` once, names the worktree
from that hash, creates it at that exact commit, and verifies the resulting
`HEAD`.

`$transfer-git-commit-to-eu3` updates this fixed ref. The shared `push_gpu`
checkout can remain on a different `HEAD`; this skill never checks it out or
resets it.

## Isolation invariants

- `push_gpu` owns the shared Git metadata but its checkout is left untouched.
- Dirty tracked or untracked files in `push_gpu` are not copied into the new
  worktree.
- New worktrees are siblings of `push_gpu`, never children of it.
- FPV worktrees use `tmp_gpu_fpv_run_<sha>`. blk_run worktrees use
  `tmp_gpu_blk_run_<sha>_<sanity|smoke|nightly>`.
- A second run of the same candidate and workflow must wait if matching
  processes are active; otherwise the high-level workflow may use guarded
  `--if-exists` cleanup before recreating it.
- Trial-only source modifications and all run artifacts stay in the isolated
  worktree and are never pushed by this skill.

## Partial setup

If component update or source generation fails, keep the worktree while
diagnosing. Verify:

```sh
git -C <worktree> rev-parse HEAD
git -C <worktree> status --short
git -C /arm/projectscratch/mpd/pj33000696_njord/users/tibger01/push_gpu \
  worktree list --porcelain
```

Use `setup_worktree.sh --resume-existing` only while `eu3-candidate` still
resolves to the same commit. The first `design/sourceme` may fail solely
because committed component revisions are not checked out yet; the script
records that status, runs `git components update --force`, and requires a
strict retry. Every naming profile then runs `design/logical/make sources` and
stops. It must not source or validate a formal, simulation, lint, or other
downstream environment.

Do not turn a partially prepared worktree into a shared reusable checkout.

## Removal

Preserve required artifacts and stop matching worktree processes before
removal. The removal script accepts only the exact workflow-specific sibling
path, verifies Git registration, and deletes only that worktree and its
temporary branch. It never removes or cleans `push_gpu`.

`remove_worktree.sh --if-exists` is the bounded pre-run form. It handles a
leftover temporary branch after worktree pruning, succeeds when nothing
remains, and refuses an unregistered directory at the expected path.
