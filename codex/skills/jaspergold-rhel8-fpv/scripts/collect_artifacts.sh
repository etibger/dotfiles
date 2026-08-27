#!/usr/bin/env bash
set -euo pipefail

repo=.
host=rhel8-VM
worktree=
run_id=

usage() {
  printf 'Usage: %s --repo PATH --worktree REMOTE_PATH --run-id ID [--host HOST]\n' "$0" >&2
}

while (($#)); do
  case "$1" in
    --repo) repo=${2:?missing value}; shift 2 ;;
    --host) host=${2:?missing value}; shift 2 ;;
    --worktree) worktree=${2:?missing value}; shift 2 ;;
    --run-id) run_id=${2:?missing value}; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) usage; printf 'Unknown argument: %s\n' "$1" >&2; exit 2 ;;
  esac
done

[[ $host =~ ^[A-Za-z0-9._-]+$ ]] || { printf 'Rejected host.\n' >&2; exit 2; }
[[ $worktree =~ ^/home/tibger01/projects/fornjot/tmp_gpu_fpv_run_[0-9a-f]{12}$ ]] || {
  printf 'Rejected worktree.\n' >&2
  exit 2
}
[[ $run_id =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || {
  printf 'Rejected run ID.\n' >&2
  exit 2
}

repo=$(git -C "$repo" rev-parse --show-toplevel)
dest="$repo/private/tmp/jaspergold-rhel8-fpv/$run_id"
mkdir -p "$dest"

remote="$host:$worktree/private/tmp/jaspergold-rhel8-fpv/$run_id/"
rsync -a --prune-empty-dirs \
  --include='*/' \
  --include='*.vcd' \
  --include='*.rpt' \
  --include='*.json' \
  --include='run.log' \
  --include='run.cmd' \
  --exclude='*' \
  "$remote" "$dest/"

printf 'LOCAL_ARTIFACT_DIR=%s\n' "$dest"
rg --files "$dest" | LC_ALL=C sort
