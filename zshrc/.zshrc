eval "$(starship init zsh)"

# Activate syntax highlighting
source $(brew --prefix)/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh
# Disable underline
(( ${+ZSH_HIGHLIGHT_STYLES} )) || typeset -A ZSH_HIGHLIGHT_STYLES
ZSH_HIGHLIGHT_STYLES[path]=none
ZSH_HIGHLIGHT_STYLES[path_prefix]=none

# Activate autosuggestions
source $(brew --prefix)/share/zsh-autosuggestions/zsh-autosuggestions.zsh

# If you come from bash you might have to change your $PATH.
# export PATH=/opt/homebrew/bin:$HOME/bin:/usr/local/bin:$PATH
export PATH="/opt/homebrew/bin:$HOME/bin:/usr/local/bin:$PATH"
export PATH="/opt/homebrew/opt/m4/bin:$PATH"
export PATH="/opt/homebrew/opt/openssl@1.1/bin:$PATH"
export PATH="/opt/homebrew/anaconda3/bin:$PATH"

export PATH="/opt/homebrew/opt/openjdk/bin:$PATH"
export PATH="$HOME/neovim/bin:$PATH"

#homebrew setup
eval "$(brew shellenv)"
alias ll="ls -lha"
alias brew_up='brew update && brew upgrade && brew upgrade --cask && brew cleanup -s && rm -rf "$(brew --cache)"'

[[ ! -f ~/.config/secrets/.secrets.zsh ]] || source ~/.config/secrets/.secrets.zsh
[ -f ~/.config/fzf/.fzf.zsh ] && source ~/.config/fzf/.fzf.zsh

export NVM_DIR="$HOME/.nvm"
[ -s "/opt/homebrew/opt/nvm/nvm.sh" ] && \. "/opt/homebrew/opt/nvm/nvm.sh"  # This loads nvm
[ -s "/opt/homebrew/opt/nvm/etc/bash_completion.d/nvm" ] && \. "/opt/homebrew/opt/nvm/etc/bash_completion.d/nvm"  # This loads nvm bash_completion

eval "$(uv generate-shell-completion zsh)"

