#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: install-aliases.sh [--dry-run]

Copy aliases.gitconfig into your global Git configuration.
Existing aliases with the same names are replaced; other settings and aliases
are preserved. The repository does not need to stay at the same path afterward.

  --dry-run   Print the commands without changing Git configuration.
  -h, --help  Show this help.
EOF
}

dry_run=0
case "${1:-}" in
  '') ;;
  --dry-run) dry_run=1; shift ;;
  -h|--help) usage; exit 0 ;;
  *) usage >&2; exit 2 ;;
esac
if (($#)); then
  usage >&2
  exit 2
fi

if ! command -v git >/dev/null 2>&1; then
  printf 'Git is required. Install Git, then rerun this script.\n' >&2
  exit 1
fi

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
aliases_file="$script_dir/aliases.gitconfig"
if ! alias_names=$(git config --file "$aliases_file" --name-only --get-regexp '^alias\.'); then
  printf 'Cannot read aliases from %s\n' "$aliases_file" >&2
  exit 1
fi

count=0
while IFS= read -r alias_name; do
  alias_value=$(git config --file "$aliases_file" --get "$alias_name")
  if ((dry_run)); then
    printf 'git config --global --replace-all %q %q\n' "$alias_name" "$alias_value"
  else
    git config --global --replace-all "$alias_name" "$alias_value"
  fi
  count=$((count + 1))
done <<< "$alias_names"

if ((!dry_run)); then
  printf 'Installed %s Git aliases in your global configuration.\n' "$count"
fi
