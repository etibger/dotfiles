alias ls='eza --icons'
alias ll='ls -la'
alias screensaver='cmatrix -ba -u 3 -C red'
alias brew_up='brew update && brew upgrade && brew upgrade --cask && brew cleanup -s && rm -rf "$(brew --cache)"'
alias rebuild_nvim='make CMAKE_BUILD_TYPE=Release CMAKE_INSTALL_PREFIX="$HOME" install'
alias git-fsmonitor-restart='/Users/tibger01/.codex/hooks/git-fsmonitor.sh restart'
alias codex-working='codex --no-daemon --no-alt-screen'

# Prefer the locally built Herdr with the copy-mode fix when installed.
if [[ -x "$HOME/.local/bin/herdr-latest-build" ]]; then
  alias herdr="$HOME/.local/bin/herdr-latest-build"
fi

# Start a fresh persistent session without changing the caller's directory.
function _herdr_general() (
  local herdr_bin="$HOME/.local/bin/herdr-latest-build"
  [[ -x "$herdr_bin" ]] || herdr_bin=$(command -v herdr) || return
  local session_name="general-$(/usr/bin/uuidgen | tr '[:upper:]' '[:lower:]')"
  local server_pid attempt
  cd "$HOME/Projects" || return
  unset HERDR_SOCKET_PATH HERDR_CLIENT_SOCKET_PATH HERDR_SESSION
  unset HERDR_PANE_ID HERDR_ENV

  HERDR_STARTUP_CWD="$PWD" "$herdr_bin" --session "$session_name" server </dev/null &
  server_pid=$!
  for attempt in {1..100}; do
    if "$herdr_bin" --session "$session_name" workspace rename w1 general >/dev/null 2>&1; then
      print -r -- "Herdr session: $session_name"
      "$herdr_bin" --session "$session_name"
      return $?
    fi
    if ! kill -0 "$server_pid" 2>/dev/null; then
      wait "$server_pid"
      return 1
    fi
    sleep 0.1
  done
  print -u2 -- "Herdr did not initialize session $session_name within 10 seconds."
  "$herdr_bin" --session "$session_name" session stop "$session_name"
  return 1
)
alias herdr-general='_herdr_general'

function h() {
  "$@" --help 2>&1 | bat --plain --language=help
}

# Company documentation build command, when work-tools is installed.
if (( $+commands[memsys-docs-make] )); then
  alias docker-make=memsys-docs-make
fi
