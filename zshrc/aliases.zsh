alias ls='eza --icons'
alias ll='ls -la'
alias screensaver='cmatrix -ba -u 3 -C red'
alias brew_up='brew update && brew upgrade && brew upgrade --cask && brew cleanup -s && rm -rf "$(brew --cache)"'
alias rebuild_nvim='make CMAKE_BUILD_TYPE=Release CMAKE_INSTALL_PREFIX="$HOME" install'

# Open the standard Arm hosts in a fresh four-tab WezTerm window.
function arm-ssh-password-save() {
  /usr/bin/security add-generic-password \
    -U \
    -a tibger01 \
    -s com.arm.ssh.tibger01 \
    -l 'Arm SSH password (tibger01)' \
    -w
}

function arm-ssh() {
  local askpass="${XDG_CONFIG_HOME:-$HOME/.config}/zshrc/ssh-askpass-keychain"

  if [[ ! -x $askpass ]]; then
    print -u2 -- "arm-ssh: missing executable helper: $askpass"
    return 1
  fi

  local -x SSH_ASKPASS=$askpass
  local -x SSH_ASKPASS_REQUIRE=force
  command ssh "$@"
}

function arm-ssh-tmux() {
  local host=$1
  shift

  arm-ssh -t "$@" "$host" \
    'exec "${SHELL:-/bin/sh}" -ic "tmux attach"'
}

function _arm-wezterm-tab() {
  local anchor_pane=$1
  local title=$2
  shift 2

  local pane_id
  pane_id=$(command wezterm cli spawn --pane-id "$anchor_pane" -- "$@") || return
  command wezterm cli set-tab-title --pane-id "$pane_id" "$title" >/dev/null
}

function arm-tabs() {
  if (( ! $+commands[wezterm] )); then
    print -u2 -- 'arm-tabs: wezterm is not available in PATH'
    return 1
  fi

  if ! /usr/bin/security find-generic-password \
    -a tibger01 \
    -s com.arm.ssh.tibger01 \
    >/dev/null 2>&1; then
    print -u2 -- 'arm-tabs: SSH password is not in Keychain; run arm-ssh-password-save first'
    return 1
  fi

  local mac_pane
  mac_pane=$(command wezterm cli spawn --new-window --cwd "$PWD" -- \
    zsh -lic 'tmux ls || tmux -u new -s MAC_HOME; exec zsh -l') || return
  command wezterm cli set-tab-title --pane-id "$mac_pane" MAC >/dev/null || return

  _arm-wezterm-tab "$mac_pane" UBUNTU zsh -lic \
    'arm-ssh-tmux tibger01@e126606.arm.com -L 5901:localhost:5901; exec zsh -l' || return
  _arm-wezterm-tab "$mac_pane" VM zsh -lic \
    'arm-ssh-tmux tibger01@e126606-vm1.arm.com; exec zsh -l' || return
  _arm-wezterm-tab "$mac_pane" EUHPC3 zsh -lic \
    'arm-ssh-tmux tibger01@login43.hpc01.eu03.arm.com; exec zsh -l' || return

  command wezterm cli activate-pane --pane-id "$mac_pane" >/dev/null
}

function h() {
  "$@" --help 2>&1 | bat --plain --language=help
}
