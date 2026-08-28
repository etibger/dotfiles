#!/usr/bin/env bash
set -euo pipefail

base_repo=/arm/projectscratch/mpd/pj33000696_njord/users/tibger01/push_gpu
worktree_root=/arm/projectscratch/mpd/pj33000696_njord/users/tibger01
candidate_ref=refs/heads/eu3-candidate
workflow=fpv
regression=
prepare=1
resume_existing=0

usage() {
  cat >&2 <<'EOF'
Usage: setup_worktree.sh [--workflow fpv|blk-run]
                         [--regression sanity|smoke|nightly]
                         [--skip-prepare] [--resume-existing]

The candidate is always the fixed refs/heads/eu3-candidate commit in push_gpu.
The default workflow is fpv. The blk-run workflow requires --regression.
EOF
}

while (($#)); do
  case "$1" in
    --workflow) workflow=${2:?missing value}; shift 2 ;;
    --regression) regression=${2:?missing value}; shift 2 ;;
    --skip-prepare) prepare=0; shift ;;
    --resume-existing) resume_existing=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) usage; printf 'Unknown argument: %s\n' "$1" >&2; exit 2 ;;
  esac
done

case "$workflow" in
  fpv)
    [[ -z $regression ]] || {
      printf '%s\n' '--regression is valid only with --workflow blk-run.' >&2
      exit 2
    }
    ;;
  blk-run)
    case "$regression" in
      sanity|smoke|nightly) ;;
      *)
        printf '%s\n' '--workflow blk-run requires --regression sanity, smoke, or nightly.' >&2
        exit 2
        ;;
    esac
    ;;
  *)
    printf 'Rejected workflow: %s\n' "$workflow" >&2
    exit 2
    ;;
esac

git -C "$base_repo" rev-parse --git-dir >/dev/null
candidate=$(git -C "$base_repo" rev-parse --verify "${candidate_ref}^{commit}")
short_sha=${candidate:0:12}

case "$workflow" in
  fpv)
    worktree="$worktree_root/tmp_gpu_fpv_run_$short_sha"
    branch="tmp_fpv_run_$short_sha"
    ;;
  blk-run)
    worktree="$worktree_root/tmp_gpu_blk_run_${short_sha}_${regression}"
    branch="tmp_blk_run_${short_sha}_${regression}"
    ;;
esac

if ((resume_existing)); then
  [[ -d $worktree ]] || {
    printf 'Cannot resume missing worktree: %s\n' "$worktree" >&2
    exit 1
  }
  git -C "$base_repo" worktree list --porcelain |
    grep -Fx "worktree $worktree" >/dev/null || {
      printf 'Existing path is not the registered candidate worktree.\n' >&2
      exit 1
    }
  current_branch=$(git -C "$worktree" symbolic-ref --short HEAD)
  [[ $current_branch == "$branch" ]] || {
    printf 'Unexpected worktree branch: %s\n' "$current_branch" >&2
    exit 1
  }
else
  [[ ! -e $worktree ]] || {
    printf 'Worktree path already exists: %s\n' "$worktree" >&2
    exit 1
  }
  if git -C "$base_repo" show-ref --verify --quiet "refs/heads/$branch"; then
    printf 'Temporary branch already exists: %s\n' "$branch" >&2
    exit 1
  fi
  git -C "$base_repo" worktree add -b "$branch" "$worktree" "$candidate"
fi

actual=$(git -C "$worktree" rev-parse HEAD)
[[ $actual == "$candidate" ]] || {
  printf 'Worktree candidate mismatch: expected=%s actual=%s\n' \
    "$candidate" "$actual" >&2
  exit 1
}

# Emit identity before preparation so callers can retain the exact worktree if
# component or workflow-specific preparation fails.
printf 'BASE_REPO=%s\n' "$base_repo"
printf 'WORKTREE=%s\n' "$worktree"
printf 'TEMP_BRANCH=%s\n' "$branch"
printf 'CANDIDATE_SHA=%s\n' "$candidate"
printf 'CANDIDATE_REF=%s\n' "$candidate_ref"
printf 'WORKFLOW=%s\n' "$workflow"
if [[ $workflow == blk-run ]]; then
  printf 'REGRESSION=%s\n' "$regression"
fi

if ((prepare)); then
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
  )
fi

printf 'PREPARED=%s\n' "$prepare"
