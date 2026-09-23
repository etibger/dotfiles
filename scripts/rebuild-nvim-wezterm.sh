#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)

"$script_dir/rebuild-nvim.sh" &
nvim_pid=$!
"$script_dir/rebuild-wezterm.sh" &
wezterm_pid=$!

nvim_status=0
wezterm_status=0
wait "$nvim_pid" || nvim_status=$?
wait "$wezterm_pid" || wezterm_status=$?

printf 'Neovim exit status: %s\nWezTerm exit status: %s\n' "$nvim_status" "$wezterm_status"
if ((nvim_status != 0 || wezterm_status != 0)); then
  exit 1
fi
