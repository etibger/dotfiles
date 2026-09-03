# Dotfiles

Personal configuration repository for shell, terminal, tmux, and window-management tooling. The tracked files show a setup centered on:

- macOS desktop tiling with AeroSpace and `borders`
- terminal-heavy workflows with WezTerm and tmux
- shell prompt customization with Starship and a retained Powerlevel10k preset
- small focused config fragments instead of one monolithic bootstrap script

This README documents the tracked directories that are **not** listed in the root `.gitignore`. Ignored directories are intentionally omitted from the detailed sections below.

## Table of Contents

- [Repository Overview](#repository-overview)
- [Backlog](#backlog)
- [What Is Tracked Here](#what-is-tracked-here)
- [Ignored Directories Omitted From This README](#ignored-directories-omitted-from-this-readme)
- [Root-Level Files](#root-level-files)
- [aerospace](#aerospace)
- [borders](#borders)
- [fzf](#fzf)
- [p10k](#p10k)
- [tmux](#tmux)
- [wezterm](#wezterm)

## Repository Overview

This repository is a personal dotfiles collection rather than a general-purpose framework. It does not contain a unified installer or a large amount of automation; instead, it keeps the active configuration for individual tools in their expected config-file formats.

A few patterns stand out across the repo:

- Terminal navigation is strongly Vim-inspired.
- Pane and workspace movement is implemented consistently across AeroSpace, tmux, and WezTerm.
- Visual styling leans on powerline-style prompts, Nerd Font glyphs, and themed status/tab bars.
- Some tools are active, while others appear to be retained as previous or alternative setups.

## Backlog

- Replace broad Codex workspace network access with a repository-scoped Unix-socket permission for Git fsmonitor. The narrower policy should permit connections to Git's `.git/fsmonitor--daemon.ipc` sockets, including sockets in linked worktree and submodule Git directories, without enabling unrelated network access. Investigate whether this can be limited to fsmonitor queries made by commands such as `git status`; a socket-path allowlist alone is process-agnostic.

## What Is Tracked Here

The current tracked tree is small and focused. At the time of writing, Git tracks:

- `aerospace/`
- `borders/`
- `fzf/`
- `p10k/`
- `tmux/`
- `wezterm/`
- `starship.toml`
- `.gitignore`
- `zshrc/.zshrc`

Only the non-ignored top-level directories get dedicated sections below.

## Ignored Directories Omitted From This README

The root `.gitignore` excludes several directories, so they are not described in detail here:

- `arm-eap/`
- `git/`
- `github-copilot/`
- `karabiner/`
- `nvim/`
- `tigervnc/`
- `zshrc/`

There are additional ignore entries for directories that are not part of the tracked tree shown above. This README stays scoped to the repository content that is both tracked and not ignored.

## Root-Level Files

### `.gitignore`

The ignore file filters out a mix of machine-specific, private, or separately-managed application configs. It is effectively being used to keep this repository selective instead of turning all of `~/.config` into tracked state.

### `starship.toml`

The root Starship config defines a gruvbox-style, powerline-shaped prompt with:

- OS, username, hostname, and current directory segments
- Git branch, commit, and status information
- language/runtime modules for common development stacks
- Docker, Conda, Pixi, and time segments
- vi-mode-aware prompt symbols

This file suggests Starship is the current prompt solution, even though the repository still keeps a Powerlevel10k configuration under `p10k/`.

## aerospace

Configuration for the [AeroSpace](https://github.com/nikitabobko/AeroSpace) tiling window manager on macOS.

### Files

- `aerospace/aerospace.toml`
- `aerospace/aerospace-workspace-overview.sh`

### What It Does

The main config defines a keyboard-driven tiling workflow with:

- tiling and accordion layouts
- small inner and outer gaps
- Vim-style focus and movement bindings using `h`, `j`, `k`, and `l`
- direct bindings for resizing, fullscreen toggling, and workspace switching
- explicit workspace-to-monitor assignments for a multi-monitor setup
- floating rules for apps such as Finder, Preview, and Calendar

The startup command launches `borders` with a gradient active-border style, so this directory is tightly coupled to the `borders/` config.

The helper script, `aerospace-workspace-overview.sh`, queries AeroSpace for all windows and prints a compact workspace summary such as which applications are open on each workspace. That script is a convenience layer for observing the current layout rather than configuring it.

## borders

Minimal wrapper config for the `borders` macOS window-border utility.

### Files

- `borders/bordersrc`

### What It Does

This script builds a small option list and invokes `borders` with:

- rounded borders
- a fixed border width
- distinct active and inactive colors
- HiDPI rendering disabled

In practice, `borders/` provides the visual focus indicator that complements AeroSpace's tiling behavior.

## fzf

Shell integration for `fzf`, scoped to Zsh.

### Files

- `fzf/.fzf.zsh`

### What It Does

This file is a bootstrap fragment rather than a full `fzf` configuration. It:

- ensures the Homebrew `fzf` binary directory is on `PATH`
- loads Zsh completions when the shell is interactive
- loads the standard `fzf` key bindings

The directory exists to keep fuzzy-finder setup modular instead of embedding it directly into the main shell config.

## p10k

Stored configuration for a Powerlevel10k prompt theme.

### Files

- `p10k/.p10k.zsh`

### What It Does

This file was generated by the Powerlevel10k wizard and defines a two-line powerline-style prompt with:

- left prompt segments for OS, current directory, version control, and prompt symbol
- a large right prompt with status and language/environment integrations
- Nerd Font separators and decorative multiline framing
- color-heavy styling and vi-mode-aware prompt behavior

This directory looks like a retained prompt preset rather than the current primary prompt system, because the repository root also contains an active-looking `starship.toml` and recent Git history indicates a move toward Starship.

## tmux

tmux configuration focused on Vim-like pane control and a styled status line.

### Files

- `tmux/tmux.conf`

### What It Does

The tmux config includes:

- reload bindings for quick iteration on the config itself
- pane splitting on `\\` and `-`
- mouse support
- Vim-style pane navigation
- vi copy mode with selection and yank bindings
- a gruvbox-material-inspired status bar
- smart pane switching that cooperates with Vim/Neovim
- large scrollback history

It also depends on external tools/plugins, notably:

- `tmux-mem-cpu-load` for status metrics
- `tmux-fuzzback` from `~/.local/tmux-plugins/tmux-fuzzback`

So `tmux/` is both a standalone config and an integration point for local tmux extensions that are not stored in this repository.

## wezterm

WezTerm terminal emulator configuration with custom keybindings, tab rendering, and event hooks.

### Files

- `wezterm/wezterm.lua`
- `wezterm/config.lua`
- `wezterm/events.lua`
- `wezterm/kanagawa-wave.png`

### What It Does

The WezTerm setup is split into a small entrypoint and supporting Lua modules:

- `wezterm.lua` loads the shared config and applies the `Kanagawa (Gogh)` color scheme.
- `config.lua` contains the main terminal configuration.
- `events.lua` registers startup behavior.
- `kanagawa-wave.png` is a theme asset stored alongside the config.

The main config defines a terminal workflow that mirrors tmux in several places:

- a leader key on `Ctrl-g`
- leader-based tab creation, navigation, renaming, and zooming
- pane splitting and pane movement bindings
- Alt-based pane resizing
- bottom-positioned tab bar with custom formatting
- bold JetBrains Mono typography and relatively large default font size
- reduced padding, long scrollback, and inactive-pane dimming

The tab formatter adds host or environment icons based on tab titles, which makes the tab bar function as a lightweight session/dashboard view.

`events.lua` currently handles GUI startup by spawning and maximizing a window. The keymap in `config.lua` also emits session-related events such as `save_session`, `load_session`, and `restore_session`, but handlers for those events are not present in the tracked files here, so that part of the workflow likely depends on local files or ignored add-ons.
