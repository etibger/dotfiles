#!/usr/bin/env bash
set -Eeuo pipefail

worktree=
run_id=
regression=

usage() {
  cat >&2 <<'EOF'
Usage: run_blk_run.sh --worktree PATH --run-id ID --regression sanity|smoke|nightly
EOF
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

while (($#)); do
  case "$1" in
    --worktree)
      (($# >= 2)) || die 'Missing value for --worktree.'
      worktree=$2
      shift 2
      ;;
    --run-id)
      (($# >= 2)) || die 'Missing value for --run-id.'
      run_id=$2
      shift 2
      ;;
    --regression)
      (($# >= 2)) || die 'Missing value for --regression.'
      regression=$2
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage
      die "Unknown argument: $1"
      ;;
  esac
done

case "$regression" in
  sanity|smoke|nightly) ;;
  *) die 'Regression must be sanity, smoke, or nightly.' ;;
esac
[[ $worktree =~ ^/home/tibger01/projects/fornjot/tmp_gpu_blk_run_[0-9a-f]{12}_${regression}$ ]] ||
  die 'Rejected worktree path.'
[[ $run_id =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || die 'Rejected run ID.'

tb_dir="$worktree/verification/tb_deploy/tb_tex"
sim_dir="$tb_dir/sim2"
task_dir="$worktree/private/tmp/to_persist/blk-run-remote/$run_id"
[[ -d $tb_dir ]] || die "Missing tb_tex directory: $tb_dir"
[[ -d $task_dir ]] || die "Missing staged task directory: $task_dir"
[[ ! -e $sim_dir ]] || die "Simulation setup already exists: $sim_dir"

cat >"$task_dir/metadata.env" <<EOF
WORKTREE=$worktree
RUN_ID=$run_id
REGRESSION=$regression
TB_DIR=$tb_dir
SIM_DIR=$sim_dir
BLK_RUN_OPTIONS=--build-clean --$regression --no-bsub --worker=local --max-jobs 10
EOF

cd "$tb_dir"
source_status=0
set +u
source ./sourceme || source_status=$?
set -u
((source_status == 0)) || die "tb_tex/sourceme returned status $source_status."
command -v blk_setup >/dev/null || die 'blk_setup is unavailable after sourcing tb_tex.'
command -v blk_run >/dev/null || die 'blk_run is unavailable after sourcing tb_tex.'

mkdir sim2
cd sim2
blk_setup

printf 'BLK_RUN_COMMAND=blk_run --build-clean --%s --no-bsub --worker=local --max-jobs 10\n' \
  "$regression"
set +e
blk_run --build-clean "--$regression" --no-bsub --worker=local --max-jobs 10 \
  2>&1 | tee "$task_dir/run.log"
blk_run_status=${PIPESTATUS[0]}
set -e

printf '%s\n' "$blk_run_status" >"$task_dir/exit-status"
printf 'REMOTE_BLK_RUN_STATUS=%s\n' "$blk_run_status"
exit "$blk_run_status"
