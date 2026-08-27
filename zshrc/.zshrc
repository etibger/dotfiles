typeset -U path PATH
path=(
  "$HOME/.cargo/bin"
  "$HOME/.local/bin"
  "$HOME/neovim/bin"
  "$HOME/bin"
  /usr/local/bin
  $path
)
case "$(uname -s),$(uname -m)" in
  Linux,x86_64|Darwin,x86_64) path=("$HOME/.local/bin/x86_64" $path) ;;
  Linux,aarch64|Darwin,arm64) path=("$HOME/.local/bin/aarch64" $path) ;;
esac
path=(
  /opt/homebrew/opt/gnu-sed/libexec/gnubin
  /opt/homebrew/opt/grep/libexec/gnubin
  /opt/homebrew/bin
  /opt/homebrew/opt/tcl-tk/bin
  $path
)

typeset -U fpath
fpath=(/opt/homebrew/share/zsh/site-functions $fpath)

export WEZTERM_THEME=nord
export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
export TCL_LIBRARY=/opt/homebrew/opt/tcl-tk/lib/tcl9.0
export TK_LIBRARY=/opt/homebrew/opt/tcl-tk/lib/tk9.0
export KEYTIMEOUT=1
export CARAPACE_BRIDGES=zsh,fish,bash,inshellisense
export FZF_CTRL_R_OPTS='--tmux center,80%,60%'
HISTFILE="$HOME/.zsh_history"
HISTSIZE=10000
SAVEHIST=10000
unset LESS

[[ -r "$HOME/.zshrc.secrets" ]] && source "$HOME/.zshrc.secrets"
[[ -r "$HOME/.config/secrets/.secrets.zsh" ]] && source "$HOME/.config/secrets/.secrets.zsh"

autoload -Uz compinit
compinit
zstyle ':completion:*' list-dirs-first true
zstyle ':completion:*' format $'\e[2;37mCompleting %d\e[m'
zstyle ':completion:*:git:*' group-order \
  'main commands' \
  'alias commands' \
  'external commands'

if (( $+commands[fzf] )); then
  source <(fzf --zsh)
fi

if (( $+commands[carapace] )); then
  source <(carapace _carapace zsh)
fi

if [[ -r /opt/homebrew/opt/fzf-tab/share/fzf-tab/fzf-tab.zsh ]]; then
  source /opt/homebrew/opt/fzf-tab/share/fzf-tab/fzf-tab.zsh
  zstyle ':fzf-tab:*' fzf-command ftb-tmux-popup
  zstyle ':fzf-tab:*' switch-group '<' '>'
  zstyle ':fzf-tab:*' query-string prefix
fi

if (( $+commands[uv] )); then
  eval "$(uv generate-shell-completion zsh)"
fi
export NVM_DIR="$HOME/.nvm"
[ -s "/opt/homebrew/opt/nvm/nvm.sh" ] && \. "/opt/homebrew/opt/nvm/nvm.sh"  # This loads nvm
[ -s "/opt/homebrew/opt/nvm/etc/bash_completion.d/nvm" ] && \. "/opt/homebrew/opt/nvm/etc/bash_completion.d/nvm"  # This loads nvm bash_completion

export MAMBA_EXE=/opt/homebrew/opt/micromamba/bin/mamba
export MAMBA_ROOT_PREFIX="$HOME/mamba"
if [[ -x $MAMBA_EXE ]]; then
  __mamba_setup="$("$MAMBA_EXE" shell hook --shell zsh --root-prefix "$MAMBA_ROOT_PREFIX" 2>/dev/null)"
  if (( $? == 0 )); then
    eval "$__mamba_setup"
  else
    alias mamba="$MAMBA_EXE"
  fi
  unset __mamba_setup
fi

source "${XDG_CONFIG_HOME:-$HOME/.config}/zshrc/aliases.zsh"
[[ -r "$HOME/.zshrc.local" ]] && source "$HOME/.zshrc.local"

bindkey -v
bindkey -M viins 'jk' vi-cmd-mode
bindkey -M viins '^A' beginning-of-line
bindkey -M viins '^E' end-of-line
bindkey -M viins '^D' delete-char
bindkey -M viins '^W' backward-kill-word
bindkey -M viins '^U' backward-kill-line
bindkey -M viins '^K' kill-line

if (( $+commands[atuin] )); then
  eval "$(atuin init zsh --disable-up-arrow)"
elif (( $+commands[fzf] )); then
  bindkey -M viins '^R' fzf-history-widget
  bindkey -M vicmd '^R' fzf-history-widget
fi

if (( $+functions[fzf-tab-complete] )); then
  bindkey -M viins '^I' fzf-tab-complete
fi

if (( $+commands[starship] )); then
  eval "$(starship init zsh)"
fi
