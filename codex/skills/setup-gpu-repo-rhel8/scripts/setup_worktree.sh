#!/usr/bin/env bash
set -euo pipefail

base_repo=/home/tibger01/projects/fornjot/a_gpu
transfer_repo=/home/tibger01/git-transfer/c_gpu.git
candidate_ref=fpv-candidate
base_ref=
prepare=1
resume_existing=0

usage() {
  printf 'Usage: %s [--candidate-ref NAME] [--base-ref origin/BRANCH] [--skip-prepare] [--resume-existing]\n' "$0" >&2
}

while (($#)); do
  case "$1" in
    --candidate-ref) candidate_ref=${2:?missing value}; shift 2 ;;
    --base-ref) base_ref=${2:?missing value}; shift 2 ;;
    --skip-prepare) prepare=0; shift ;;
    --resume-existing) resume_existing=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) usage; printf 'Unknown argument: %s\n' "$1" >&2; exit 2 ;;
  esac
done

[[ $candidate_ref =~ ^[A-Za-z0-9][A-Za-z0-9._/-]*$ && $candidate_ref != *..* ]] || {
  printf 'Rejected candidate ref: %s\n' "$candidate_ref" >&2
  exit 2
}
if [[ -n $base_ref ]]; then
  [[ $base_ref =~ ^origin/[A-Za-z0-9][A-Za-z0-9._/-]*$ && $base_ref != *..* ]] || {
    printf 'Rejected base ref: %s\n' "$base_ref" >&2
    exit 2
  }
fi

git -C "$base_repo" rev-parse --git-dir >/dev/null
candidate=$(git --git-dir="$transfer_repo" rev-parse --verify \
  "refs/heads/$candidate_ref^{commit}")
short_sha=${candidate:0:12}
local_candidate_ref="refs/codex/fpv-candidate-$short_sha"

git -C "$base_repo" fetch "$transfer_repo" \
  "refs/heads/$candidate_ref:$local_candidate_ref"
fetched=$(git -C "$base_repo" rev-parse --verify "$local_candidate_ref^{commit}")
[[ $fetched == "$candidate" ]] || {
  printf 'Fetched candidate mismatch.\n' >&2
  exit 1
}

if [[ -z $base_ref ]]; then
  closest_distance=
  consider_ref() {
    local ref=$1
    local ref_only candidate_only distance
    [[ $ref == origin/HEAD ]] && return
    read -r ref_only candidate_only < <(
      git -C "$base_repo" rev-list --left-right --count "$ref...$candidate"
    )
    distance=$((ref_only + candidate_only))
    if [[ -z $closest_distance || $distance -lt $closest_distance ]]; then
      base_ref=$ref
      closest_distance=$distance
    fi
  }

  found_boundary=0
  while IFS= read -r boundary; do
    found_boundary=1
    while IFS= read -r ref; do
      ref=${ref#${ref%%[![:space:]]*}}
      [[ -n $ref ]] && consider_ref "$ref"
    done < <(git -C "$base_repo" branch -r --contains "$boundary")
  done < <(
    git -C "$base_repo" rev-list "$candidate" --not --remotes --boundary |
      sed -n 's/^-//p'
  )

  if (( ! found_boundary )); then
    while IFS= read -r ref; do
      ref=${ref#${ref%%[![:space:]]*}}
      [[ -n $ref ]] && consider_ref "$ref"
    done < <(git -C "$base_repo" branch -r --contains "$candidate")
  fi
fi

if [[ -n $base_ref ]]; then
  git -C "$base_repo" rev-parse --verify "$base_ref^{commit}" >/dev/null
  worktree_start=$base_ref
else
  base_ref=NO_KNOWN_ORIGIN_ANCESTOR
  worktree_start=$candidate
fi

worktree="/home/tibger01/projects/fornjot/tmp_gpu_fpv_run_$short_sha"
branch="tmp_fpv_run_$short_sha"
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
  git -C "$base_repo" worktree add -b "$branch" "$worktree" "$worktree_start"
  git -C "$worktree" reset --hard "$candidate"
fi
actual=$(git -C "$worktree" rev-parse HEAD)
[[ $actual == "$candidate" ]] || {
  printf 'Worktree candidate mismatch: expected=%s actual=%s\n' "$candidate" "$actual" >&2
  exit 1
}

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
    cd ../../verification/formal/fb_tex_flt
    set +u
    source ./sourceme
    set -u
    command -v ftrun >/dev/null
  )
fi

printf 'WORKTREE=%s\n' "$worktree"
printf 'TEMP_BRANCH=%s\n' "$branch"
printf 'CANDIDATE_SHA=%s\n' "$candidate"
printf 'BASE_REF=%s\n' "$base_ref"
printf 'PREPARED=%s\n' "$prepare"
