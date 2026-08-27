#!/usr/bin/env bash
set -euo pipefail

repo=.
host=rhel8-VM
remote_ref=fpv-candidate
remote_repo=git-transfer/c_gpu.git
dry_run=0

usage() {
  printf 'Usage: %s [--repo PATH] [--host HOST] [--remote-ref NAME] [--dry-run]\n' "$0" >&2
}

while (($#)); do
  case "$1" in
    --repo) repo=${2:?missing value for --repo}; shift 2 ;;
    --host) host=${2:?missing value for --host}; shift 2 ;;
    --remote-ref) remote_ref=${2:?missing value for --remote-ref}; shift 2 ;;
    --dry-run) dry_run=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) usage; printf 'Unknown argument: %s\n' "$1" >&2; exit 2 ;;
  esac
done

[[ $host =~ ^[A-Za-z0-9._-]+$ ]] || {
  printf 'Unsafe SSH host token: %s\n' "$host" >&2
  exit 2
}
[[ $remote_ref =~ ^[A-Za-z0-9][A-Za-z0-9._/-]*$ ]] || {
  printf 'Unsafe remote ref: %s\n' "$remote_ref" >&2
  exit 2
}
[[ $remote_ref != *..* && $remote_ref != */.lock && $remote_ref != *'@{'* ]] || {
  printf 'Rejected remote ref: %s\n' "$remote_ref" >&2
  exit 2
}

repo=$(git -C "$repo" rev-parse --show-toplevel)
candidate=$(git -C "$repo" rev-parse --verify 'HEAD^{commit}')

if ! git -C "$repo" diff --quiet --ignore-submodules=all -- ||
   ! git -C "$repo" diff --cached --quiet --ignore-submodules=all --; then
  printf 'Tracked changes exist; commit or remove them before transferring HEAD.\n' >&2
  exit 1
fi

closest_ref=
closest_distance=
closest_ref_only=
closest_candidate_only=

consider_ref() {
  local ref=$1
  local ref_only candidate_only distance
  [[ $ref == origin/HEAD ]] && return
  read -r ref_only candidate_only < <(
    git -C "$repo" rev-list --left-right --count "$ref...$candidate"
  )
  distance=$((ref_only + candidate_only))
  if [[ -z $closest_distance || $distance -lt $closest_distance ]]; then
    closest_ref=$ref
    closest_distance=$distance
    closest_ref_only=$ref_only
    closest_candidate_only=$candidate_only
  fi
}

found_boundary=0
while IFS= read -r boundary; do
  found_boundary=1
  while IFS= read -r ref; do
    ref=${ref#${ref%%[![:space:]]*}}
    [[ -n $ref ]] && consider_ref "$ref"
  done < <(git -C "$repo" branch -r --contains "$boundary")
done < <(
  git -C "$repo" rev-list "$candidate" --not --remotes --boundary |
    sed -n 's/^-//p'
)

if (( ! found_boundary )); then
  while IFS= read -r ref; do
    ref=${ref#${ref%%[![:space:]]*}}
    [[ -n $ref ]] && consider_ref "$ref"
  done < <(git -C "$repo" branch -r --contains "$candidate")
fi

if (( ! dry_run )); then
  ssh -o BatchMode=yes "$host" true
  git -C "$repo" push --force "$host:$remote_repo" \
    "$candidate:refs/heads/$remote_ref"

  remote_candidate=$(ssh -o BatchMode=yes "$host" \
    git --git-dir="$remote_repo" rev-parse --verify "refs/heads/$remote_ref^{commit}")
  if [[ $remote_candidate != "$candidate" ]]; then
    printf 'Remote verification mismatch: local=%s remote=%s\n' \
      "$candidate" "$remote_candidate" >&2
    exit 1
  fi
fi

printf 'CANDIDATE_SHA=%s\n' "$candidate"
printf 'REMOTE_HOST=%s\n' "$host"
printf 'REMOTE_REPO=%s\n' "$remote_repo"
printf 'REMOTE_REF=refs/heads/%s\n' "$remote_ref"
printf 'CLOSEST_ORIGIN_REF=%s\n' "${closest_ref:-UNKNOWN}"
if [[ -n $closest_distance ]]; then
  printf 'CLOSEST_ORIGIN_DISTANCE=%s\n' "$closest_distance"
  printf 'CLOSEST_ORIGIN_ONLY=%s\n' "$closest_ref_only"
  printf 'CANDIDATE_ONLY=%s\n' "$closest_candidate_only"
fi
printf 'REMOTE_VERIFIED=%s\n' "$((! dry_run))"
