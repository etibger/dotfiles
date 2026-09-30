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

function h() {
  "$@" --help 2>&1 | bat --plain --language=help
}

# Company documentation build command, when work-tools is installed.
if (( $+commands[memsys-docs-make] )); then
  alias docker-make=memsys-docs-make
fi
