#!/usr/bin/env bash
set -euo pipefail

base_repo=/home/tibger01/projects/fornjot/a_gpu
worktree=
confirmed=0

while (($#)); do
  case "$1" in
    --worktree) worktree=${2:?missing value}; shift 2 ;;
    --yes) confirmed=1; shift ;;
    -h|--help)
      printf 'Usage: %s --worktree /home/tibger01/projects/fornjot/tmp_gpu_fpv_run_<sha> --yes\n' "$0"
      exit 0 ;;
    *) printf 'Unknown argument: %s\n' "$1" >&2; exit 2 ;;
  esac
done

((confirmed)) || { printf 'Refusing removal without --yes.\n' >&2; exit 2; }
[[ $worktree =~ ^/home/tibger01/projects/fornjot/tmp_gpu_fpv_run_([0-9a-f]{12})$ ]] || {
  printf 'Rejected worktree path: %s\n' "$worktree" >&2
  exit 2
}
short_sha=${BASH_REMATCH[1]}
branch="tmp_fpv_run_$short_sha"

git -C "$base_repo" worktree list --porcelain | grep -Fx "worktree $worktree" >/dev/null || {
  printf 'Path is not a registered worktree: %s\n' "$worktree" >&2
  exit 1
}
if ps -u "$(id -u)" -o command= | grep -F "$worktree" | grep -E '(ftrun|jasper|jg )' >/dev/null; then
  printf 'An active formal process refers to this worktree; stop it first.\n' >&2
  exit 1
fi

git -C "$base_repo" worktree remove --force "$worktree"
if git -C "$base_repo" show-ref --verify --quiet "refs/heads/$branch"; then
  git -C "$base_repo" branch -D "$branch"
fi
git -C "$base_repo" update-ref -d "refs/codex/fpv-candidate-$short_sha"
printf 'REMOVED_WORKTREE=%s\n' "$worktree"
