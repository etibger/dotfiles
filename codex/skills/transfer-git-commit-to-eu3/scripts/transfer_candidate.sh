#!/usr/bin/env bash
set -euo pipefail

repo=.
host=eu3
remote_ref=eu3-candidate
remote_repo=/arm/projectscratch/mpd/pj33000696_njord/users/tibger01/push_gpu/
askpass="${XDG_CONFIG_HOME:-$HOME/.config}/zshrc/ssh-askpass-keychain"
dry_run=0

usage() {
  printf 'Usage: %s [--repo PATH] [--remote-ref NAME] [--dry-run]\n' "$0" >&2
}

git_local() {
  command git -c core.fsmonitor=false "$@"
}

while (($#)); do
  case "$1" in
    --repo) repo=${2:?missing value for --repo}; shift 2 ;;
    --remote-ref) remote_ref=${2:?missing value for --remote-ref}; shift 2 ;;
    --dry-run) dry_run=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) usage; printf 'Unknown argument: %s\n' "$1" >&2; exit 2 ;;
  esac
done

[[ $remote_ref =~ ^[A-Za-z0-9][A-Za-z0-9._/-]*$ ]] || {
  printf 'Unsafe remote ref: %s\n' "$remote_ref" >&2
  exit 2
}
[[ $remote_ref != *..* && $remote_ref != */.lock && $remote_ref != *'@{'* ]] || {
  printf 'Rejected remote ref: %s\n' "$remote_ref" >&2
  exit 2
}

repo=$(git_local -C "$repo" rev-parse --show-toplevel)
candidate=$(git_local -C "$repo" rev-parse --verify 'HEAD^{commit}')

if ! git_local -C "$repo" diff --quiet --ignore-submodules=all -- ||
   ! git_local -C "$repo" diff --cached --quiet --ignore-submodules=all --; then
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
    git_local -C "$repo" rev-list --left-right --count "$ref...$candidate"
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
  done < <(git_local -C "$repo" branch -r --contains "$boundary")
done < <(
  git_local -C "$repo" rev-list "$candidate" --not --remotes --boundary |
    sed -n 's/^-//p'
)

if (( ! found_boundary )); then
  while IFS= read -r ref; do
    ref=${ref#${ref%%[![:space:]]*}}
    [[ -n $ref ]] && consider_ref "$ref"
  done < <(git_local -C "$repo" branch -r --contains "$candidate")
fi

if (( ! dry_run )); then
  [[ -x $askpass ]] || {
    printf 'Missing executable SSH askpass helper: %s\n' "$askpass" >&2
    exit 1
  }
  if ! /usr/bin/security find-generic-password \
    -a tibger01 -s com.arm.ssh.tibger01 >/dev/null 2>&1; then
    printf 'Arm SSH password is not in Keychain; run arm-ssh-password-save first.\n' >&2
    exit 1
  fi

  export SSH_ASKPASS=$askpass
  export SSH_ASKPASS_REQUIRE=force

  ssh -o BatchMode=no -o PubkeyAuthentication=no \
    -o PreferredAuthentications=password,keyboard-interactive \
    -o NumberOfPasswordPrompts=1 "$host" true
  GIT_SSH_COMMAND='ssh -o BatchMode=no -o PubkeyAuthentication=no -o PreferredAuthentications=password,keyboard-interactive -o NumberOfPasswordPrompts=1' \
    git_local -C "$repo" push --force "$host:$remote_repo" \
      "$candidate:refs/heads/$remote_ref"

  remote_candidate=$(ssh -o BatchMode=no -o PubkeyAuthentication=no \
    -o PreferredAuthentications=password,keyboard-interactive \
    -o NumberOfPasswordPrompts=1 "$host" git -C "$remote_repo" rev-parse --verify \
      "refs/heads/$remote_ref^{commit}")
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
