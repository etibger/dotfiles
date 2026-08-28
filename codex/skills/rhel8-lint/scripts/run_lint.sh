#!/usr/bin/env bash
set -Eeuo pipefail

readonly base_repo=/home/tibger01/projects/fornjot/push_gpu
readonly worktree_root=/home/tibger01/projects/fornjot

candidate=
run_id=
attempt_token=
task_dir=
worktree=
stage=PRECHECK
overall_status=INITIALIZING
setup_status=NOT_RUN
lint_process_status=NOT_RUN
setup_exit_status=NOT_RUN
lint_exit_status=NOT_RUN
executor_exit_status=1
base_checkout_unchanged=UNKNOWN
finalized=0

usage() {
  cat >&2 <<'EOF'
Usage: run_lint.sh --commit FULL_SHA --run-id ID --attempt-token TOKEN

Create one retained, detached RHEL8 worktree from push_gpu's SHA-specific
campaign ref, prepare it through make sources, and run TEX Superlint.
EOF
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

write_status() {
  [[ -n ${task_dir:-} && -d $task_dir ]] || return 0
  cat >"$task_dir/status.env" <<EOF
SCHEMA_VERSION=1
RUN_ID=$run_id
CANDIDATE_SHA=$candidate
ATTEMPT_TOKEN=$attempt_token
REMOTE_REPO=$base_repo
REMOTE_WORKTREE=$worktree
REMOTE_WORKTREE_RETAINED=1
STAGE=$stage
OVERALL_STATUS=$overall_status
SETUP_STATUS=$setup_status
SETUP_EXIT_STATUS=$setup_exit_status
LINT_PROCESS_STATUS=$lint_process_status
LINT_EXIT_STATUS=$lint_exit_status
BASE_CHECKOUT_UNCHANGED=$base_checkout_unchanged
EXECUTOR_EXIT_STATUS=$executor_exit_status
EOF
}

base_checkout_is_unchanged() {
  local head_after status_after
  head_after=$(git -C "$base_repo" rev-parse --verify 'HEAD^{commit}') || return 1
  status_after=$(git -C "$base_repo" status --porcelain=v1 --untracked-files=no) || return 1
  [[ $head_after == "$base_head_before" && $status_after == "$base_status_before" ]]
}

record_worktree_status() {
  [[ -n ${task_dir:-} && -d $task_dir && -n ${worktree:-} && -d $worktree ]] || return 0
  git -C "$worktree" status --short >"$task_dir/worktree-status.txt" 2>&1 || true
}

on_exit() {
  local status=$?
  if (( ! finalized )); then
    executor_exit_status=$status
    if [[ $overall_status == INITIALIZING ]]; then
      overall_status=EXECUTOR_ERROR
    fi
    if [[ -n ${base_head_before:-} ]]; then
      if base_checkout_is_unchanged; then
        base_checkout_unchanged=1
      else
        base_checkout_unchanged=0
        overall_status=BASE_CHECKOUT_CHANGED
      fi
    fi
    record_worktree_status
    write_status || true
  fi
  printf 'REMOTE_WORKTREE=%s\n' "${worktree:-NOT_CREATED}"
  printf 'REMOTE_TASK_DIR=%s\n' "${task_dir:-NOT_CREATED}"
  printf 'REMOTE_WORKTREE_RETAINED=1\n'
  printf 'RHEL8_LINT_EXECUTOR_STATUS=%s\n' "$overall_status"
}
trap on_exit EXIT

while (($#)); do
  case "$1" in
    --commit)
      (($# >= 2)) || die 'Missing value for --commit.'
      candidate=${2,,}
      shift 2
      ;;
    --run-id)
      (($# >= 2)) || die 'Missing value for --run-id.'
      run_id=$2
      shift 2
      ;;
    --attempt-token)
      (($# >= 2)) || die 'Missing value for --attempt-token.'
      attempt_token=$2
      shift 2
      ;;
    -h|--help)
      trap - EXIT
      usage
      exit 0
      ;;
    *)
      usage
      die "Unknown argument: $1"
      ;;
  esac
done

[[ $candidate =~ ^[0-9a-f]{40}$ ]] || die '--commit must be a full 40-digit SHA.'
[[ $run_id =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || die 'Rejected run ID.'
[[ $attempt_token =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$ ]] || die 'Rejected attempt token.'

candidate_ref="refs/codex/validation-campaign/rhel8-lint/$candidate"
short_sha=${candidate:0:12}
worktree="$worktree_root/tmp_gpu_lint_run_${short_sha}_$attempt_token"
[[ $worktree =~ ^/home/tibger01/projects/fornjot/tmp_gpu_lint_run_[0-9a-f]{12}_[A-Za-z0-9][A-Za-z0-9._-]{0,95}$ ]] ||
  die 'Derived worktree failed its exact-path guard.'

git -C "$base_repo" rev-parse --git-dir >/dev/null 2>&1 ||
  die "Handoff repository is unavailable: $base_repo"
base_top=$(git -C "$base_repo" rev-parse --show-toplevel)
base_top=$(cd "$base_top" && pwd -P)
[[ $base_top == "$base_repo" ]] ||
  die "Handoff repository resolved outside the allowed path: $base_top"

resolved_candidate=$(git -C "$base_repo" rev-parse --verify "$candidate_ref^{commit}") ||
  die "Candidate ref is missing from push_gpu: $candidate_ref"
[[ $resolved_candidate == "$candidate" ]] ||
  die "Candidate ref mismatch: expected=$candidate actual=$resolved_candidate"

base_head_before=$(git -C "$base_repo" rev-parse --verify 'HEAD^{commit}')
base_status_before=$(git -C "$base_repo" status --porcelain=v1 --untracked-files=no)

if [[ -e $worktree ]]; then
  overall_status=BLOCKED_EXISTING_WORKTREE
  die "Retained worktree path already exists; refusing to clean or reuse it: $worktree"
fi
if git -C "$base_repo" worktree list --porcelain |
   grep -Fx "worktree $worktree" >/dev/null; then
  overall_status=BLOCKED_REGISTERED_WORKTREE
  die "Worktree is already registered; refusing to clean or reuse it: $worktree"
fi

stage=CREATE_WORKTREE
git -C "$base_repo" worktree add --detach "$worktree" "$candidate_ref"
git -C "$base_repo" worktree list --porcelain |
  grep -Fx "worktree $worktree" >/dev/null ||
  die 'New worktree is not registered with push_gpu.'
worktree_top=$(git -C "$worktree" rev-parse --show-toplevel)
worktree_top=$(cd "$worktree_top" && pwd -P)
[[ $worktree_top == "$worktree" ]] || die 'New worktree resolved outside its guarded path.'
actual_candidate=$(git -C "$worktree" rev-parse --verify 'HEAD^{commit}')
[[ $actual_candidate == "$candidate" ]] ||
  die "Worktree candidate mismatch: expected=$candidate actual=$actual_candidate"

task_dir="$worktree/private/tmp/to_persist/rhel8-lint/$run_id"
mkdir -p "$task_dir"
cat >"$task_dir/metadata.env" <<EOF
SCHEMA_VERSION=1
RUN_ID=$run_id
CANDIDATE_SHA=$candidate
ATTEMPT_TOKEN=$attempt_token
CANDIDATE_REF=$candidate_ref
REMOTE_REPO=$base_repo
REMOTE_REPO_HEAD_BEFORE=$base_head_before
REMOTE_WORKTREE=$worktree
REMOTE_WORKTREE_RETAINED=1
SETUP_BOUNDARY=design/logical/make_sources
LINT_DIRECTORY=design/work/shader_core/exec_core/tex/lint
LINT_COMMAND='dcs_superlint superlint_8x/configuration_top.yaml'
EOF
write_status

stage=SETUP_THROUGH_MAKE_SOURCES
overall_status=RUNNING_SETUP
write_status
set +e
(
  cd "$worktree/design"
  initial_source_status=0
  set +u
  source ./sourceme || initial_source_status=$?
  set -u
  if ((initial_source_status)); then
    printf 'Initial design sourceme returned %s; updating committed components before strict retry.\n' \
      "$initial_source_status"
  fi
  git components update --force
  set +u
  source ./sourceme
  set -u
  cd logical
  make sources
) 2>&1 | tee "$task_dir/setup.log"
setup_exit_status=${PIPESTATUS[0]}
set -e

if ((setup_exit_status != 0)); then
  setup_status=FAIL
  overall_status=SETUP_FAILED
  executor_exit_status=$setup_exit_status
  if base_checkout_is_unchanged; then
    base_checkout_unchanged=1
  else
    base_checkout_unchanged=0
    overall_status=BASE_CHECKOUT_CHANGED
    executor_exit_status=1
  fi
  record_worktree_status
  write_status
  finalized=1
  exit "$executor_exit_status"
fi
setup_status=PASS

stage=TEX_SUPERLINT
overall_status=RUNNING_LINT
write_status
set +e
(
  cd "$worktree/design"
  set +u
  source ./sourceme
  set -u
  command -v dcs_superlint >/dev/null || {
    printf 'dcs_superlint is unavailable after sourcing design/sourceme.\n' >&2
    exit 127
  }
  cd work/shader_core/exec_core/tex/lint
  [[ -f superlint_8x/configuration_top.yaml ]] || {
    printf 'Missing Superlint configuration: superlint_8x/configuration_top.yaml\n' >&2
    exit 1
  }
  printf 'LINT_COMMAND=dcs_superlint superlint_8x/configuration_top.yaml\n'
  dcs_superlint superlint_8x/configuration_top.yaml
) 2>&1 | tee "$task_dir/lint.log"
lint_exit_status=${PIPESTATUS[0]}
set -e

# Retain small machine-readable Arm Lint evidence beside the executor metadata.
# The large run database stays in the retained worktree.
lint_directory="$worktree/design/work/shader_core/exec_core/tex/lint"
report_root="$lint_directory/arm_lint_run/vithar_tex_top.noset"
report_artifact_dir="$task_dir/reports"
mkdir -p "$report_artifact_dir"
for report_relative in \
  arm_lint_db/flow/eda.log \
  arm_lint_db/flow/summary.yaml \
  arm_lint_db/flow/results.yaml \
  arm_lint_db/eda/report.xml \
  arm_lint_db/eda/report.waiver.xml; do
  report_source="$report_root/$report_relative"
  if [[ -f $report_source ]]; then
    mkdir -p "$report_artifact_dir/$(dirname "$report_relative")"
    cp -Lp "$report_source" "$report_artifact_dir/$report_relative"
  fi
done
find "$report_artifact_dir" -type f -print | sort >"$task_dir/report-files.txt"

if ((lint_exit_status == 0)); then
  lint_process_status=PASS
  overall_status=COMPLETE
  executor_exit_status=0
else
  lint_process_status=FAIL
  overall_status=LINT_FAILED
  executor_exit_status=$lint_exit_status
fi

if base_checkout_is_unchanged; then
  base_checkout_unchanged=1
else
  base_checkout_unchanged=0
  overall_status=BASE_CHECKOUT_CHANGED
  executor_exit_status=1
fi

stage=COMPLETE
record_worktree_status
write_status
finalized=1
exit "$executor_exit_status"
