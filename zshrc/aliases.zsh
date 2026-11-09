alias ls='eza --icons'
alias ll='ls -la'
alias screensaver='cmatrix -ba -u 3 -C red'
alias brew_up='brew update && brew upgrade && brew upgrade --cask && brew cleanup -s && rm -rf "$(brew --cache)"'
alias rebuild_nvim='make CMAKE_BUILD_TYPE=Release CMAKE_INSTALL_PREFIX="$HOME" install'
alias git-fsmonitor-restart='/Users/tibger01/.codex/hooks/git-fsmonitor.sh restart'
alias codex-working='codex --no-daemon --no-alt-screen'
alias omp-working='NODE_USE_SYSTEM_CA=1 omp --model arm-proxy/gpt-6.1-sol'
alias start_devcon='../../gpu-devcontainer/docker-run-custom tibger01'

# Repository commands are implemented in personal-tools.
alias harmonize-gitea="$HOME/Projects/personal-tools/bin/harmonize-gitea"
alias harmonize-github-issues="$HOME/Projects/personal-tools/bin/harmonize-github-issues"
alias publish-both="$HOME/Projects/personal-tools/bin/publish-both"

# Prefer the locally built Herdr with the copy-mode fix when installed.
if [[ -x "$HOME/.local/bin/herdr-latest-build" ]]; then
  alias herdr="$HOME/.local/bin/herdr-latest-build"
fi

# Start a fresh persistent session without changing the caller's directory.
alias _herdr_general="$HOME/Projects/personal-tools/bin/herdr-general"
alias herdr-general="$HOME/Projects/personal-tools/bin/herdr-general"

if [[ "$OSTYPE" == darwin* ]]; then
  function _herdr_attach_general() (
    local herdr_bin="$HOME/.local/bin/herdr-latest-build"
    [[ -x "$herdr_bin" ]] || herdr_bin=$(command -v herdr) || return
    local sessions_json matching_names session_name
    local -a session_names
    unset HERDR_SOCKET_PATH HERDR_CLIENT_SOCKET_PATH HERDR_SESSION
    unset HERDR_PANE_ID HERDR_ENV
    sessions_json=$("$herdr_bin" session list --json) || return
    matching_names=$(print -r -- "$sessions_json" | jq -r '.sessions[] | select(.name | startswith("general")) | .name') || return
    if [[ -z "$matching_names" ]]; then
      print -u2 -- 'No general Herdr session was found; starting one.'
      _herdr_general
      return $?
    fi
    session_names=("${(@f)matching_names}")
    if (( ${#session_names} == 1 )); then
      session_name="$session_names[1]"
    else
      local PS3='Herdr session (Ctrl-D to cancel): '
      print -u2 -- 'Several general Herdr sessions are available; choose one to attach:'
      select session_name in "${session_names[@]}"; do
        [[ -n "$session_name" ]] && break
        print -u2 -- 'Enter a session number from the list.'
      done
      [[ -n "$session_name" ]] || return 1
    fi
    "$herdr_bin" session attach "$session_name"
  )
fi

function h() {
  "$@" --help 2>&1 | bat --plain --language=help
}

# Company documentation build command, when work-tools is installed.
if (( $+commands[memsys-docs-make] )); then
  alias docker-make=memsys-docs-make
fi
