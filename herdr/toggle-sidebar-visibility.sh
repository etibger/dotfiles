#!/usr/bin/env bash
set -euo pipefail

config_root=${XDG_CONFIG_HOME:-"$HOME/.config"}
config_path=${HERDR_CONFIG_PATH:-"$config_root/herdr/config.toml"}
herdr_bin=${HERDR_BIN_PATH:-herdr}

mode=$(
  sed -n 's/^[[:space:]]*sidebar_collapsed_mode[[:space:]]*=[[:space:]]*"\([^"]*\)"[[:space:]]*$/\1/p' \
    "$config_path" | head -n 1
)

case "$mode" in
  compact)
    next_mode=hidden
    ;;
  hidden)
    next_mode=compact
    ;;
  *)
    printf 'toggle-sidebar-visibility: expected compact or hidden mode, found %s\n' \
      "${mode:-unset}" >&2
    exit 1
    ;;
esac

HERDR_SIDEBAR_FROM=$mode HERDR_SIDEBAR_TO=$next_mode \
  perl -0pi -e '
    s/^sidebar_collapsed_mode = "\Q$ENV{HERDR_SIDEBAR_FROM}\E"$/sidebar_collapsed_mode = "$ENV{HERDR_SIDEBAR_TO}"/m
      or die "sidebar mode changed before update\n";
  ' "$config_path"

"$herdr_bin" server reload-config >/dev/null
