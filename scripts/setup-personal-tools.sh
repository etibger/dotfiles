#!/usr/bin/env bash
set -euo pipefail

repo="$HOME/Projects/personal-tools"
bin_dir="$HOME/.local/bin"

if [[ ! -e "$repo" ]]; then
  mkdir -p "$(dirname "$repo")"
  git clone git@github.com:etibger/personal-tools.git "$repo"
elif [[ ! -d "$repo/.git" ]]; then
  printf 'Existing path is not a Git checkout: %s\n' "$repo" >&2
  exit 1
fi

mkdir -p "$bin_dir"
for script in "$repo"/bin/*; do
  [[ -f "$script" && -x "$script" ]] || continue
  target="$bin_dir/${script##*/}"
  if [[ -L "$target" && $(readlink "$target") == "$script" ]]; then
    printf 'Already linked: %s\n' "$target"
  elif [[ -e "$target" || -L "$target" ]]; then
    printf 'Review existing command: %s\n' "$target" >&2
  else
    ln -s "$script" "$target"
    printf 'Linked: %s -> %s\n' "$target" "$script"
  fi
done

printf 'Ensure %s is on PATH (the .config Zsh setup includes it).\n' "$bin_dir"
