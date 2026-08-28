#!/usr/bin/env bash
set -euo pipefail

base_repo=/arm/projectscratch/mpd/pj33000696_njord/users/tibger01/push_gpu
worktree=
workflow=fpv
regression=
confirmed=0
if_exists=0

while (($#)); do
  case "$1" in
    --worktree) worktree=${2:?missing value}; shift 2 ;;
    --workflow) workflow=${2:?missing value}; shift 2 ;;
    --regression) regression=${2:?missing value}; shift 2 ;;
    --if-exists) if_exists=1; shift ;;
    --yes) confirmed=1; shift ;;
    -h|--help)
      cat <<'EOF'
Usage: remove_worktree.sh --worktree PATH [--workflow fpv|blk-run]
                          [--regression sanity|smoke|nightly]
                          [--if-exists] --yes

The default workflow is fpv. The blk-run workflow requires --regression.
--if-exists also succeeds when no matching temporary worktree or branch
remains.
EOF
      exit 0 ;;
    *) printf 'Unknown argument: %s\n' "$1" >&2; exit 2 ;;
  esac
done

((confirmed)) || { printf 'Refusing removal without --yes.\n' >&2; exit 2; }
case "$workflow" in
  fpv)
    [[ -z $regression ]] || {
      printf '%s\n' '--regression is valid only with --workflow blk-run.' >&2
      exit 2
    }
    [[ $worktree =~ ^/arm/projectscratch/mpd/pj33000696_njord/users/tibger01/tmp_gpu_fpv_run_([0-9a-f]{12})$ ]] || {
      printf 'Rejected FPV worktree path: %s\n' "$worktree" >&2
      exit 2
    }
    short_sha=${BASH_REMATCH[1]}
    branch="tmp_fpv_run_$short_sha"
    process_pattern='(ftrun|jasper|jg )'
    ;;
  blk-run)
    case "$regression" in
      sanity|smoke|nightly) ;;
      *)
        printf '%s\n' '--workflow blk-run requires --regression sanity, smoke, or nightly.' >&2
        exit 2
        ;;
    esac
    [[ $worktree =~ ^/arm/projectscratch/mpd/pj33000696_njord/users/tibger01/tmp_gpu_blk_run_([0-9a-f]{12})_${regression}$ ]] || {
      printf 'Rejected blk-run worktree path: %s\n' "$worktree" >&2
      exit 2
    }
    short_sha=${BASH_REMATCH[1]}
    branch="tmp_blk_run_${short_sha}_${regression}"
    process_pattern='(blk_run|blk_val|xrun|xmsim|irun|xmelab|xmvlog)'
    ;;
  *)
    printf 'Rejected workflow: %s\n' "$workflow" >&2
    exit 2
    ;;
esac

registered=0
path_exists=0
branch_exists=0
git -C "$base_repo" worktree list --porcelain |
  grep -Fx "worktree $worktree" >/dev/null && registered=1
[[ -e $worktree ]] && path_exists=1
git -C "$base_repo" show-ref --verify --quiet "refs/heads/$branch" && branch_exists=1

if ((path_exists && ! registered)); then
  printf 'Path exists but is not the registered temporary worktree; refusing removal: %s\n' \
    "$worktree" >&2
  exit 1
fi
if ((! registered && ! branch_exists)); then
  if ((if_exists)); then
    printf 'NOTHING_TO_REMOVE=%s\n' "$worktree"
    exit 0
  fi
  printf 'Path is not a registered worktree: %s\n' "$worktree" >&2
  exit 1
fi
if ((! registered && ! if_exists)); then
  printf 'Path is not a registered worktree: %s\n' "$worktree" >&2
  exit 1
fi

process_list=
if ! process_list=$(ps -u "$(id -u)" -o command=); then
  printf 'Unable to inspect active processes; refusing worktree removal.\n' >&2
  exit 1
fi
if printf '%s\n' "$process_list" |
  awk -v worktree="$worktree" -v process_pattern="$process_pattern" '
    {
      command = $0
      while ((offset = index(command, worktree)) != 0) {
        command = substr(command, 1, offset - 1) \
          substr(command, offset + length(worktree))
      }
      if (index($0, worktree) != 0 && command ~ process_pattern) {
        found = 1
      }
    }
    END { exit(found ? 0 : 1) }
  '; then
  printf 'An active %s process refers to this worktree; stop it first.\n' "$workflow" >&2
  exit 1
fi

if ((registered)); then
  git -C "$base_repo" worktree remove --force "$worktree"
fi
if ((branch_exists)); then
  git -C "$base_repo" branch -D "$branch"
fi
printf 'REMOVED_WORKTREE=%s\n' "$worktree"
