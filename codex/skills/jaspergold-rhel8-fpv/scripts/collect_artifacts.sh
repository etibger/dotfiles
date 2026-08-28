#!/usr/bin/env bash
set -euo pipefail

repo=.
host=rhel8-VM
worktree=
run_id=
include_vcd=0

usage() {
  printf 'Usage: %s --repo PATH --worktree REMOTE_PATH --run-id ID [--host rhel8-VM] [--include-vcd]\n' "$0" >&2
}

while (($#)); do
  case "$1" in
    --repo) repo=${2:?missing value}; shift 2 ;;
    --host) host=${2:?missing value}; shift 2 ;;
    --worktree) worktree=${2:?missing value}; shift 2 ;;
    --run-id) run_id=${2:?missing value}; shift 2 ;;
    --include-vcd) include_vcd=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) usage; printf 'Unknown argument: %s\n' "$1" >&2; exit 2 ;;
  esac
done

[[ $host == rhel8-VM ]] || { printf 'Only rhel8-VM is supported.\n' >&2; exit 2; }
[[ $worktree =~ ^/home/tibger01/projects/fornjot/tmp_gpu_fpv_run_[0-9a-f]{12}(_[A-Za-z0-9][A-Za-z0-9._-]{0,63})?$ ]] || {
  printf 'Rejected worktree.\n' >&2
  exit 2
}
[[ $run_id =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || {
  printf 'Rejected run ID.\n' >&2
  exit 2
}

repo=$(git -c core.fsmonitor=false -C "$repo" rev-parse --show-toplevel)
dest="$repo/private/tmp/to_persist/jaspergold-rhel8-fpv/$run_id"
mkdir -p "$dest"

remote="$host:$worktree/private/tmp/to_persist/jaspergold-rhel8-fpv/$run_id/"
include_args=(
  --exclude='report-venv/***'
  --exclude='uv-cache/***'
  --include='*/'
  --include='*.rpt'
  --include='*.tsv'
  --include='*.json'
  --include='*.yaml'
  --include='run.log'
  --include='run.cmd'
  --exclude='*'
)
if ((include_vcd)); then
  include_args=(
    --exclude='report-venv/***'
    --exclude='uv-cache/***'
    --include='*/'
    --include='*.vcd'
    --include='*.rpt'
    --include='*.tsv'
    --include='*.json'
    --include='*.yaml'
    --include='run.log'
    --include='run.cmd'
    --exclude='*'
  )
fi

rsync -a -e 'ssh -o BatchMode=yes -o ConnectTimeout=15' --prune-empty-dirs \
  "${include_args[@]}" "$remote" "$dest/"

printf 'LOCAL_ARTIFACT_DIR=%s\n' "$dest"
printf 'VCD_COLLECTION=%s\n' "$include_vcd"
find "$dest" -type f -print | LC_ALL=C sort
