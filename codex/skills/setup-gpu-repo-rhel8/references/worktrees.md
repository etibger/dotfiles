# RHEL8 push_gpu worktree rules

## Candidate selection

The candidate is read from `refs/heads/<candidate-ref>` in
`/home/tibger01/projects/fornjot/push_gpu`. A high-level workflow should use a
SHA-specific ref so simultaneous FPV and simulation transfers cannot overwrite
one another. The manager checkout and its `HEAD` are irrelevant and remain
untouched.

## Isolation

- Create worktrees as siblings of `push_gpu`, never inside it.
- Verify the worktree `HEAD` equals the candidate resolved before creation.
- Do not copy dirty files from the manager checkout.
- Keep generated databases, waves, logs, and trial-only modifications inside
  the workflow worktree. Large artifacts stay on RHEL8 unless requested for
  debugging.
- A pre-existing exact path or temporary branch is a stop condition. Do not
  delete it automatically; inspect or explicitly clean it first.

## Partial setup

The first `design/sourceme` may fail because components are not yet checked
out. The script records that result, runs `git components update --force`,
requires the second source to succeed, runs `design/logical/make sources`, and
stops. For recovery verify the exact SHA, branch, and Git worktree registration
before using `--resume-existing`.

## Removal

Removal is a separate, explicitly requested operation. The guard accepts only
the exact profile-specific sibling path, rejects unregistered directories,
and refuses removal while a matching formal or simulation process names that
worktree. It removes the registered worktree and temporary branch only; it
does not delete handoff refs or touch `push_gpu`'s checkout.
