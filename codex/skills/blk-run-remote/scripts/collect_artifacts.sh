#!/usr/bin/env bash
set -Eeuo pipefail

repo=
host=rhel8-VM
worktree=
run_id=
regression=

usage() {
  cat >&2 <<'EOF'
Usage: collect_artifacts.sh --repo PATH --host rhel8-VM --worktree PATH --run-id ID --regression sanity|smoke|nightly
EOF
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

while (($#)); do
  case "$1" in
    --repo) (($# >= 2)) || die 'Missing value for --repo.'; repo=$2; shift 2 ;;
    --host) (($# >= 2)) || die 'Missing value for --host.'; host=$2; shift 2 ;;
    --worktree) (($# >= 2)) || die 'Missing value for --worktree.'; worktree=$2; shift 2 ;;
    --run-id) (($# >= 2)) || die 'Missing value for --run-id.'; run_id=$2; shift 2 ;;
    --regression) (($# >= 2)) || die 'Missing value for --regression.'; regression=$2; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) usage; die "Unknown argument: $1" ;;
  esac
done

[[ $host == rhel8-VM ]] || die 'Only rhel8-VM is currently supported.'
case "$regression" in
  sanity|smoke|nightly) ;;
  *) die 'Regression must be sanity, smoke, or nightly.' ;;
esac
[[ $worktree =~ ^/home/tibger01/projects/fornjot/tmp_gpu_blk_run_[0-9a-f]{12}_${regression}$ ]] ||
  die 'Rejected worktree path.'
[[ $run_id =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || die 'Rejected run ID.'

repo=$(git -C "$repo" rev-parse --show-toplevel)
dest="$repo/private/tmp/to_persist/blk-run-remote/$run_id"
mkdir -p "$dest" "$dest/sim2"

ssh_transport='ssh -o BatchMode=yes -o ConnectTimeout=15'
remote_task="$host:$worktree/private/tmp/to_persist/blk-run-remote/$run_id/"
rsync -a -e "$ssh_transport" "$remote_task" "$dest/"

remote_sim="$host:$worktree/verification/tb_deploy/tb_tex/sim2/"
rsync -a -e "$ssh_transport" --prune-empty-dirs --max-size=20m \
  --include='*/' \
  --include='*.log' \
  --include='*.rpt' \
  --include='*.txt' \
  --include='*.json' \
  --include='*.xml' \
  --include='*.cfg' \
  --include='*.config' \
  --include='*.yaml' \
  --include='*.yml' \
  --exclude='*' \
  "$remote_sim" "$dest/sim2/"

printf 'LOCAL_ARTIFACT_DIR=%s\n' "$dest"
find "$dest" -type f -print | LC_ALL=C sort
