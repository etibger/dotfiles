# RHEL8 GPU worktree rules

## Selecting the base

Prefer the `CLOSEST_ORIGIN_REF` calculated in the source repository. It
minimizes symmetric commit distance among origin branches containing the
candidate's nearest origin-reachable boundary commit, so the origin branch may
have advanced since the topic forked. Pass it explicitly to the setup script.
If none was found, omit `--base-ref`; the remote script performs the same search
against refs already present in `a_gpu`.

Do not fetch every origin branch merely to refresh this calculation. The
candidate transfer already sends all objects reachable from the candidate,
and a broad fetch can be disproportionately slow in this repository.

## Isolation invariants

- `a_gpu` owns the shared Git metadata but its dirty checkout is left untouched.
- Existing `b_gpu`, `tmp_gpu`, and `tmp2_gpu` worktrees are never cleaned,
  reset, checked out, or removed.
- The new worktree starts at the selected base to establish branch context,
  then is reset to the exact transferred candidate. The base need not be an
  ancestor when it advanced after the candidate forked.
- All injected properties, wrappers, run logs, and results are kept in the new
  worktree. Trial-only source modifications remain uncommitted and unpushed.

## Partial setup

If component update or source generation fails, keep the worktree while
diagnosing. Verify these before retrying:

```sh
git -C <worktree> rev-parse HEAD
git -C <worktree> status --short
git -C <worktree> worktree list
```

Then use `setup_worktree.sh --resume-existing` with the same candidate and base
ref. The first `design/sourceme` may return nonzero solely because committed
component revisions have not been checked out yet. The script records that
status, runs `git components update --force`, and requires a second source to
succeed before source generation.

Do not turn a partially prepared worktree into a shared reusable checkout.

## Removal

Remove only the exact hash-named worktree created for the run. Stop any process
whose command line refers to it, preserve requested artifacts, then use the
guarded removal script. Removal intentionally discards uncommitted trial
assertions and repository-local proof outputs.
