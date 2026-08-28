#!/usr/bin/env bash
set -Eeuo pipefail

readonly local_repo=/Users/tibger01/Projects/Fornjot/a_gpu
readonly default_host=rhel8-VM
readonly future_password_host=login43.hpc01.eu03.arm.com
readonly remote_candidate_ref_prefix=blk-run-candidate
readonly remote_worktree_root=/home/tibger01/projects/fornjot
readonly fixed_max_jobs=10

readonly skills_root=/Users/tibger01/.config/codex/skills
readonly transfer_script="$skills_root/transfer-git-commit-to-rhel8/scripts/transfer_candidate.sh"
readonly setup_script="$skills_root/setup-gpu-repo-rhel8/scripts/setup_worktree.sh"
readonly remove_script="$skills_root/setup-gpu-repo-rhel8/scripts/remove_worktree.sh"
readonly script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
readonly remote_runner="$script_dir/run_blk_run.sh"
readonly collect_script="$script_dir/collect_artifacts.sh"

commit=
regression=
host=$default_host
dry_run=0
recovery_worktree=

usage() {
  cat <<'EOF'
Usage: run_remote_blk_run.sh --commit SHA --regression sanity|smoke|nightly [--host rhel8-VM] [--dry-run]

Run an isolated tb_tex blk_run regression. The candidate must be current HEAD
of /Users/tibger01/Projects/Fornjot/a_gpu. The command uses build-clean, local
workers, no bsub, and a fixed max-jobs value of 10.

Options:
  --commit SHA            Candidate commit (7-40 hexadecimal characters)
  --regression TYPE       sanity, smoke, or nightly
  --host HOST             Remote host (default and current support: rhel8-VM)
  --dry-run               Validate locally and print the resolved plan
  -h, --help              Show this help
EOF
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

report_retained_worktree() {
  local status=$?
  if ((status != 0)) && [[ -n $recovery_worktree ]]; then
    printf 'RECOVERY_WORKTREE=%s\n' "$recovery_worktree" >&2
  fi
}

trap report_retained_worktree EXIT

while (($#)); do
  case "$1" in
    --commit)
      (($# >= 2)) || die 'Missing value for --commit.'
      commit=$2
      shift 2
      ;;
    --regression)
      (($# >= 2)) || die 'Missing value for --regression.'
      regression=$2
      shift 2
      ;;
    --host)
      (($# >= 2)) || die 'Missing value for --host.'
      host=$2
      shift 2
      ;;
    --dry-run)
      dry_run=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      die "Unknown argument: $1"
      ;;
  esac
done

[[ -n $commit ]] || die '--commit is required.'
[[ $commit =~ ^[0-9A-Fa-f]{7,40}$ ]] ||
  die '--commit must be a 7-40 digit hexadecimal SHA.'
case "$regression" in
  sanity|smoke|nightly) ;;
  *) die '--regression must be sanity, smoke, or nightly.' ;;
esac
case "$host" in
  "$default_host") ;;
  "$future_password_host")
    die "$future_password_host is reserved for future support; password/Keychain authentication and HPC execution are not enabled."
    ;;
  *) die "Unsupported host: $host (current support: $default_host)." ;;
esac

git -C "$local_repo" rev-parse --git-dir >/dev/null 2>&1 ||
  die "Fixed local repository is unavailable: $local_repo"
for required_file in \
  "$transfer_script" \
  "$setup_script" \
  "$remote_runner" \
  "$collect_script" \
  "$remove_script"; do
  [[ -f $required_file ]] || die "Required workflow file is missing: $required_file"
done
[[ -x $transfer_script ]] || die "Transfer helper is not executable: $transfer_script"

candidate=$(git -C "$local_repo" rev-parse --verify "$commit^{commit}") ||
  die "Cannot resolve candidate commit: $commit"
head_sha=$(git -C "$local_repo" rev-parse --verify 'HEAD^{commit}')
[[ $candidate == "$head_sha" ]] ||
  die "Requested commit is not current HEAD (requested=$candidate HEAD=$head_sha)."

short_sha=${candidate:0:12}
remote_candidate_ref="$remote_candidate_ref_prefix-$short_sha"
expected_worktree="$remote_worktree_root/tmp_gpu_blk_run_${short_sha}_${regression}"
local_artifact_root="$local_repo/private/tmp/to_persist/blk-run-remote"
ssh_options=(
  -o BatchMode=yes
  -o ConnectTimeout=15
  -o ServerAliveInterval=30
  -o ServerAliveCountMax=4
)

if ((dry_run)); then
  transfer_output=$("$transfer_script" \
    --repo "$local_repo" \
    --host "$host" \
    --remote-ref "$remote_candidate_ref" \
    --dry-run)
  printf '%s\n' "$transfer_output"
  printf 'MODE=DRY_RUN\n'
  printf 'LOCAL_REPO=%s\n' "$local_repo"
  printf 'CANDIDATE_SHA=%s\n' "$candidate"
  printf 'REMOTE_HOST=%s\n' "$host"
  printf 'REMOTE_CANDIDATE_REF=%s\n' "$remote_candidate_ref"
  printf 'REMOTE_WORKTREE=%s\n' "$expected_worktree"
  printf 'REGRESSION=%s\n' "$regression"
  printf 'BLK_RUN_MAX_JOBS=%s\n' "$fixed_max_jobs"
  printf 'BLK_RUN_COMMAND=blk_run --build-clean --%s --no-bsub --worker=local --max-jobs %s\n' \
    "$regression" "$fixed_max_jobs"
  printf 'PRE_RUN_CLEANUP=guarded-if-exists\n'
  printf 'LOCAL_ARTIFACT_ROOT=%s\n' "$local_artifact_root"
  exit 0
fi

timestamp=$(date -u +%Y%m%dT%H%M%SZ)
run_id="tb-tex-${regression}-${short_sha}-${timestamp}-$$"
local_artifact_dir="$local_artifact_root/$run_id"
mkdir -p "$local_artifact_dir"

printf 'RUN_ID=%s\n' "$run_id"
printf 'REMOTE_HOST=%s\n' "$host"
printf 'REGRESSION=%s\n' "$regression"
printf 'LOCAL_ARTIFACT_DIR=%s\n' "$local_artifact_dir"

printf 'Cleaning any prior exact worktree and branch for %s/%s.\n' \
  "$short_sha" "$regression"
set +e
ssh "${ssh_options[@]}" "$host" bash -s -- \
  --worktree "$expected_worktree" \
  --workflow blk-run \
  --regression "$regression" \
  --if-exists \
  --yes \
  <"$remove_script" 2>&1 | tee "$local_artifact_dir/pre-cleanup.log"
pre_cleanup_status=${PIPESTATUS[0]}
set -e
((pre_cleanup_status == 0)) ||
  die "Guarded pre-run cleanup failed with status $pre_cleanup_status."

printf 'Transferring candidate %s to %s.\n' "$candidate" "$host"
set +e
"$transfer_script" \
  --repo "$local_repo" \
  --host "$host" \
  --remote-ref "$remote_candidate_ref" 2>&1 |
  tee "$local_artifact_dir/transfer.log"
transfer_status=${PIPESTATUS[0]}
set -e
((transfer_status == 0)) || die "Candidate transfer failed with status $transfer_status."

transferred_sha=$(awk -F= '$1 == "CANDIDATE_SHA" { value=$2 } END { print value }' \
  "$local_artifact_dir/transfer.log")
closest_ref=$(awk -F= '$1 == "CLOSEST_ORIGIN_REF" { value=$2 } END { print value }' \
  "$local_artifact_dir/transfer.log")
[[ $transferred_sha == "$candidate" ]] ||
  die "Transferred SHA mismatch (expected=$candidate actual=${transferred_sha:-MISSING})."
if [[ $closest_ref != UNKNOWN ]]; then
  [[ $closest_ref =~ ^origin/[A-Za-z0-9][A-Za-z0-9._/-]*$ && $closest_ref != *..* ]] ||
    die "Transfer helper returned an unsafe origin ref: $closest_ref"
fi

printf 'Preparing isolated worktree %s.\n' "$expected_worktree"
setup_args=(
  --workflow blk-run
  --regression "$regression"
  --candidate-ref "$remote_candidate_ref"
)
if [[ $closest_ref != UNKNOWN ]]; then
  setup_args+=(--base-ref "$closest_ref")
fi
set +e
ssh "${ssh_options[@]}" "$host" bash -s -- "${setup_args[@]}" \
  <"$setup_script" 2>&1 | tee "$local_artifact_dir/setup.log"
setup_status=${PIPESTATUS[0]}
set -e

worktree=$(awk -F= '$1 == "WORKTREE" { value=$2 } END { print value }' \
  "$local_artifact_dir/setup.log")
prepared_sha=$(awk -F= '$1 == "CANDIDATE_SHA" { value=$2 } END { print value }' \
  "$local_artifact_dir/setup.log")
if [[ $worktree == "$expected_worktree" ]]; then
  recovery_worktree=$worktree
fi
((setup_status == 0)) || die "Remote worktree setup failed with status $setup_status."
[[ $worktree == "$expected_worktree" ]] ||
  die "Remote worktree mismatch (expected=$expected_worktree actual=${worktree:-MISSING})."
[[ $prepared_sha == "$candidate" ]] ||
  die "Prepared SHA mismatch (expected=$candidate actual=${prepared_sha:-MISSING})."
recovery_worktree=$worktree

remote_task_dir="$worktree/private/tmp/to_persist/blk-run-remote/$run_id"
printf 'Staging the remote runner in %s.\n' "$remote_task_dir"
ssh "${ssh_options[@]}" "$host" mkdir -p "$remote_task_dir"
scp "${ssh_options[@]}" "$remote_runner" "$host:$remote_task_dir/"

printf 'Starting the %s regression with local workers and max-jobs %s.\n' \
  "$regression" "$fixed_max_jobs"
set +e
ssh "${ssh_options[@]}" "$host" \
  bash "$remote_task_dir/run_blk_run.sh" \
  --worktree "$worktree" \
  --run-id "$run_id" \
  --regression "$regression" 2>&1 |
  tee "$local_artifact_dir/remote-session.log"
blk_run_status=${PIPESTATUS[0]}
set -e
printf 'REMOTE_BLK_RUN_STATUS=%s\n' "$blk_run_status"

printf 'Collecting console output and small regression result files.\n'
set +e
"$collect_script" \
  --repo "$local_repo" \
  --host "$host" \
  --worktree "$worktree" \
  --run-id "$run_id" \
  --regression "$regression" 2>&1 |
  tee "$local_artifact_dir/collect.log"
collect_status=${PIPESTATUS[0]}
set -e
if ((collect_status != 0)); then
  die "Artifact collection failed with status $collect_status; the worktree was retained."
fi

[[ -s $local_artifact_dir/run.log ]] ||
  die 'Collected run.log is missing or empty; the worktree was retained.'
if ((blk_run_status != 0)); then
  die "Remote blk_run returned status $blk_run_status; artifacts were collected and the worktree was retained."
fi

printf 'Removing the verified, artifact-preserved worktree %s.\n' "$worktree"
set +e
ssh "${ssh_options[@]}" "$host" bash -s -- \
  --worktree "$worktree" \
  --workflow blk-run \
  --regression "$regression" \
  --yes \
  <"$remove_script" 2>&1 | tee "$local_artifact_dir/cleanup.log"
cleanup_status=${PIPESTATUS[0]}
set -e
((cleanup_status == 0)) ||
  die "Guarded worktree cleanup failed with status $cleanup_status."

recovery_worktree=
printf 'REMOTE_WORKTREE_REMOVED=%s\n' "$worktree"
printf 'LOCAL_ARTIFACT_DIR=%s\n' "$local_artifact_dir"
printf 'REMOTE_BLK_RUN_COMPLETE=1\n'
