#!/usr/bin/env bash
set -euo pipefail

kind=
task=
dry_run=0

usage() {
  cat <<'EOF'
Usage: cleanup-repo-task-tmp.sh --kind to_clean|to_persist --task NAME [--dry-run]

Remove one direct task directory below the current Git repository's
private/tmp/to_clean/ or private/tmp/to_persist/ directory.
EOF
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

while (($#)); do
  case "$1" in
    --kind)
      (($# >= 2)) || die 'Missing value for --kind.'
      kind=$2
      shift 2
      ;;
    --task)
      (($# >= 2)) || die 'Missing value for --task.'
      task=$2
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

case "$kind" in
  to_clean|to_persist) ;;
  *) die '--kind must be to_clean or to_persist.' ;;
esac
[[ $task =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] ||
  die '--task must be one safe directory name containing only letters, digits, dot, underscore, or hyphen.'
[[ $task != . && $task != .. ]] || die '--task cannot be dot or dot-dot.'

repo=$(git rev-parse --show-toplevel 2>/dev/null) ||
  die 'Run this command from inside the Git repository that owns the task directory.'
repo_real=$(cd "$repo" && pwd -P)
[[ $repo_real != / ]] || die 'Refusing to operate on the filesystem root.'

expected_base="$repo_real/private/tmp/$kind"
target="$expected_base/$task"
if [[ ! -e $target && ! -L $target ]]; then
  printf 'ALREADY_ABSENT=%s\n' "$target"
  exit 0
fi

[[ -d $expected_base ]] || die "Expected temporary parent is not a directory: $expected_base"
base_real=$(cd "$expected_base" && pwd -P)
[[ $base_real == "$expected_base" ]] ||
  die "Temporary parent resolves outside its literal repository path: $expected_base"
[[ ! -L $target ]] || die "Refusing to remove a symbolic-link task path: $target"
[[ -d $target ]] || die "Task path is not a directory: $target"

target_real=$(cd "$target" && pwd -P)
[[ $target_real == "$base_real/$task" ]] ||
  die "Task path does not resolve to the requested direct child: $target"

if ((dry_run)); then
  printf 'WOULD_REMOVE=%s\n' "$target_real"
  exit 0
fi

/bin/rm -rf -- "$target_real"
[[ ! -e $target_real && ! -L $target_real ]] ||
  die "Task directory still exists after removal: $target_real"
printf 'REMOVED_TASK_TMP=%s\n' "$target_real"
