#!/usr/bin/env bash
set -euo pipefail

source_dir=${WEZTERM_SOURCE_DIR:-$HOME/tmp/wezterm}
bin_dir=${WEZTERM_BIN_DIR:-$HOME/bin}
target_dir=${CARGO_TARGET_DIR:-$source_dir/target}
installed_binary=$bin_dir/wezterm

report_binary() {
  local active output status=0
  active=$(command -v wezterm || true)

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
  printf 'WezTerm checkout has local changes: %s\n' "$source_dir" >&2
  exit 1
fi

printf '\nWezTerm before update\n'
report_binary || true
old_head=$(git rev-parse HEAD)

printf 'Updating WezTerm in %s\n' "$source_dir"
git pull --ff-only
new_head=$(git rev-parse HEAD)
git submodule update --init --recursive
git clean -xfd ./
cargo build --release -p wezterm -p wezterm-gui -p wezterm-mux-server

if [[ $target_dir != /* ]]; then
  target_dir=$source_dir/$target_dir
fi

for binary in wezterm wezterm-gui wezterm-mux-server; do
  if [[ ! -x $target_dir/release/$binary ]]; then
    printf 'Missing built binary: %s\n' "$target_dir/release/$binary" >&2
    exit 1
  fi
done

mkdir -p "$bin_dir"
for binary in wezterm wezterm-gui wezterm-mux-server; do
  install -m 755 "$target_dir/release/$binary" "$bin_dir/$binary"
done

printf '\nWezTerm after install\n'
report_status=0
report_binary || report_status=$?
printf 'Other installed binaries: %s, %s\n' "$bin_dir/wezterm-gui" "$bin_dir/wezterm-mux-server"

printf '\nWezTerm commits pulled (%s..%s)\n' "${old_head:0:10}" "${new_head:0:10}"
if [[ $old_head == "$new_head" ]]; then
  printf 'No new commits pulled.\n'
else
  git log --date=short --format='%h %ad %s' "$old_head..$new_head"
fi

exit "$report_status"
