#!/usr/bin/env bash
set -euo pipefail

source_dir=${NVIM_SOURCE_DIR:-$HOME/tmp/neovim}
install_prefix=${NVIM_INSTALL_PREFIX:-$HOME}
installed_binary=$install_prefix/bin/nvim

report_binary() {
  local active output status=0
  active=$(command -v nvim || true)

  printf 'On PATH: %s\n' "${active:-not found}"
  printf 'Install destination: %s\n' "$installed_binary"
  if [[ -x $installed_binary ]]; then
    if output=$("$installed_binary" --version 2>&1); then
      printf 'Installed version: %s\n' "${output%%$'\n'*}"
    else
      printf 'Installed version: unavailable (%s)\n' "${output%%$'\n'*}"
      status=1
    fi
  else
    printf 'Installed version: not installed\n'
    status=1
  fi

  if [[ -n $active && $active != "$installed_binary" ]]; then
    if output=$("$active" --version 2>&1); then
      printf 'PATH version: %s\n' "${output%%$'\n'*}"
    else
      printf 'PATH version: unavailable (%s)\n' "${output%%$'\n'*}"
    fi
  fi
  return "$status"
}

cd "$source_dir"

if [[ -n $(git status --porcelain) ]]; then
  printf 'Neovim checkout has local changes: %s\n' "$source_dir" >&2
  exit 1
fi

printf '\nNeovim before update\n'
report_binary || true
old_head=$(git rev-parse HEAD)

printf 'Updating Neovim in %s\n' "$source_dir"
git pull --ff-only
new_head=$(git rev-parse HEAD)
make clean
make CMAKE_BUILD_TYPE=Release CMAKE_INSTALL_PREFIX="$install_prefix" install

printf '\nNeovim after install\n'
report_status=0
report_binary || report_status=$?

printf '\nNeovim commits pulled (%s..%s)\n' "${old_head:0:10}" "${new_head:0:10}"
if [[ $old_head == "$new_head" ]]; then
  printf 'No new commits pulled.\n'
else
  git log --date=short --format='%h %ad %s' "$old_head..$new_head"
fi

exit "$report_status"
