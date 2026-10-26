alias ls='eza --icons'
alias ll='ls -la'
alias screensaver='cmatrix -ba -u 3 -C red'
alias brew_up='brew update && brew upgrade && brew upgrade --cask && brew cleanup -s && rm -rf "$(brew --cache)"'
alias rebuild_nvim='make CMAKE_BUILD_TYPE=Release CMAKE_INSTALL_PREFIX="$HOME" install'
alias git-fsmonitor-restart='/Users/tibger01/.codex/hooks/git-fsmonitor.sh restart'
alias codex-working='codex --no-daemon --no-alt-screen'
alias start_devcon='../../gpu-devcontainer/docker-run-custom tibger01'

# Fast-forward a branch from GitHub, then mirror it to Gitea.
function harmonize-gitea() {
  local branch=${1:-main}
  local origin_ref="refs/remotes/origin/$branch"
  local gitea_ref="refs/remotes/gitea/$branch"

  if (( $# > 1 )); then
    print -u2 -- "Usage: harmonize-gitea [branch]"
    return 2
  fi
  if ! git check-ref-format --branch "$branch" >/dev/null 2>&1; then
    print -u2 -- "harmonize-gitea: invalid branch name: $branch"
    return 2
  fi
  if ! git remote get-url origin >/dev/null 2>&1 || ! git remote get-url gitea >/dev/null 2>&1; then
    print -u2 -- 'harmonize-gitea: expected remotes named origin and gitea'
    return 1
  fi

  print -r -- "Fetching '$branch' from origin and gitea..."
  git fetch origin "$branch:$origin_ref" || {
    print -u2 -- "harmonize-gitea: could not fetch '$branch' from origin; stopping."
    return 1
  }
  git fetch gitea "$branch:$gitea_ref" || {
    print -u2 -- "harmonize-gitea: could not fetch '$branch' from gitea; stopping."
    return 1
  }

  if ! git show-ref --verify --quiet "$origin_ref"; then
    print -u2 -- "harmonize-gitea: origin has no branch '$branch'; stopping."
    return 1
  fi
  if ! git show-ref --verify --quiet "$gitea_ref"; then
    print -u2 -- "harmonize-gitea: gitea has no branch '$branch'; stopping."
    return 1
  fi
  if ! git merge-base --is-ancestor "$gitea_ref" "$origin_ref"; then
    print -u2 -- "harmonize-gitea: gitea/$branch is not an ancestor of origin/$branch."
    print -u2 -- 'The remote histories differ or gitea has commits missing from origin; no push was made.'
    return 1
  fi

  print -r -- "Remote histories are compatible: gitea/$branch can fast-forward to origin/$branch."
  git switch "$branch" || return
  git merge --ff-only "$origin_ref" || {
    print -u2 -- "harmonize-gitea: local '$branch' cannot fast-forward to origin/$branch; no push was made."
    return 1
  }
  git push gitea "$branch"
}

# Push a local branch to both remotes only when their starting tips match.
function publish-both() {
  local branch=${1:-main}
  local local_ref="refs/heads/$branch"
  local origin_ref="refs/remotes/origin/$branch"
  local gitea_ref="refs/remotes/gitea/$branch"
  local origin_tip gitea_tip local_tip

  if (( $# > 1 )); then
    print -u2 -- "Usage: publish-both [branch]"
    return 2
  fi
  if ! git check-ref-format --branch "$branch" >/dev/null 2>&1; then
    print -u2 -- "publish-both: invalid branch name: $branch"
    return 2
  fi
  if ! git remote get-url origin >/dev/null 2>&1 || ! git remote get-url gitea >/dev/null 2>&1; then
    print -u2 -- 'publish-both: expected remotes named origin and gitea'
    return 1
  fi
  if ! git show-ref --verify --quiet "$local_ref"; then
    print -u2 -- "publish-both: local branch '$branch' does not exist; nothing was pushed."
    return 1
  fi

  print -r -- "Fetching '$branch' from origin and gitea..."
  git fetch origin "$branch:$origin_ref" || {
    print -u2 -- "publish-both: could not fetch '$branch' from origin; nothing was pushed."
    return 1
  }
  git fetch gitea "$branch:$gitea_ref" || {
    print -u2 -- "publish-both: could not fetch '$branch' from gitea; nothing was pushed."
    return 1
  }

  origin_tip=$(git rev-parse --verify "$origin_ref^{commit}") || return 1
  gitea_tip=$(git rev-parse --verify "$gitea_ref^{commit}") || return 1
  local_tip=$(git rev-parse --verify "$local_ref^{commit}") || return 1

  if [[ "$origin_tip" != "$gitea_tip" ]]; then
    print -u2 -- "publish-both: origin/$branch and gitea/$branch have different tips."
    print -u2 -- "origin: $origin_tip"
    print -u2 -- "gitea:  $gitea_tip"
    print -u2 -- 'No push was made; inspect and reconcile the remote branches first.'
    return 1
  fi
  if ! git merge-base --is-ancestor "$origin_ref" "$local_ref"; then
    print -u2 -- "publish-both: local '$branch' is not a fast-forward of both remote branches."
    print -u2 -- 'No push was made; inspect the local and remote histories first.'
    return 1
  fi
  if [[ "$local_tip" == "$origin_tip" ]]; then
    print -r -- "publish-both: local '$branch' already matches both remotes; nothing to push."
    return 0
  fi

  print -r -- "Checks passed: both remotes are at $origin_tip and local '$branch' can fast-forward them to $local_tip."
  print -r -- 'Pushing to origin...'
  git push origin "${local_ref}:refs/heads/${branch}" || {
    print -u2 -- 'publish-both: push to origin failed; gitea was not pushed.'
    return 1
  }
  print -r -- 'Pushing to gitea...'
  git push gitea "${local_ref}:refs/heads/${branch}" || {
    print -u2 -- 'publish-both: push to gitea failed after origin succeeded; the remotes may now differ.'
    return 1
  }
  print -r -- "publish-both: pushed '$branch' to origin and gitea."
}

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

  HERDR_STARTUP_CWD="$PWD" "$herdr_bin" --session "$session_name" server </dev/null >/dev/null 2>&1 &
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
