# Zsh configuration

This directory contains the tracked Zsh configuration. The configuration is
written for Zsh on macOS with Apple Silicon Homebrew installed under
`/opt/homebrew`.

## Installation

Install all Homebrew-managed tools used by the configuration:

```sh
brew install \
  atuin \
  carapace \
  cmatrix \
  eza \
  fzf \
  fzf-tab \
  gnu-sed \
  grep \
  micromamba \
  starship \
  tcl-tk \
  tmux \
  uv
```

Zsh is included with macOS. The `rebuild_nvim` alias also expects `make` from
the Xcode Command Line Tools and a Neovim source checkout at `$HOME/neovim`.

## Dependencies

| Tool | Purpose | Behavior when missing |
| --- | --- | --- |
| Zsh | Shell, completion, history, and key bindings | Required |
| Homebrew | Installs tools and provides paths under `/opt/homebrew` | Homebrew-specific paths and `brew_up` will not work |
| Atuin | Primary interactive history search | Fzf handles Ctrl-R instead |
| Fzf | Shell integration and fallback history search | Fzf bindings are skipped |
| fzf-tab | Fuzzy tab completion | Tab keeps its normal Zsh behavior |
| Carapace | Multi-shell command completion | Carapace completion is skipped |
| Starship | Prompt | Zsh uses its existing prompt |
| uv | Zsh completion for uv commands | uv completion is skipped |
| micromamba | Mamba initialization and the `oai` alias | Mamba setup and `oai` will not work |
| eza | Implementation of the `ls` and `ll` aliases | Those aliases fail when invoked |
| cmatrix | `screensaver` alias | That alias fails when invoked |
| GNU grep and GNU sed | GNU-compatible tools placed first in `PATH` | System implementations remain available |
| Tcl/Tk | Tcl/Tk binaries and library variables | Tcl/Tk-dependent programs may not work |
| tmux | Popup UI used by Fzf and fzf-tab | Popup behavior is unavailable outside tmux |

Most integrations are guarded, so the shell still starts when an optional tool
is absent. Aliases are resolved only when invoked.

## Activation

Keep `~/.zshrc` as a small machine-local loader:

```zsh
source "$HOME/.config/zshrc/.zshrc"
```

This is preferable to a symlink because installers can append machine-local
setup to `~/.zshrc` without modifying the tracked file.

## Secrets

Private environment variables and aliases belong in `~/.zshrc.secrets`. The
tracked configuration sources this file when it exists:

```zsh
export SERVICE_API_KEY="replace-with-a-real-key"
```

Protect it with:

```sh
chmod 600 "$HOME/.zshrc.secrets"
```

The secrets file lives outside this repository and must not be committed.

## History

Atuin provides the primary history search. Native Zsh history is also retained
in `~/.zsh_history` as a fallback, with up to 10,000 commands kept in memory and
on disk.

## PATH assumptions

The configuration adds Homebrew's GNU grep, GNU sed, and Tcl/Tk directories,
plus `$HOME/.cargo/bin`, `$HOME/.local/bin`, `$HOME/neovim/bin`, and
`$HOME/bin`. It also selects an architecture-specific directory under
`$HOME/.local/bin` for x86-64 or Arm binaries.
