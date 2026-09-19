# Herdr configuration

This directory contains the portable Herdr configuration and helper scripts.

## Keep tab names indexed

The local `tab-index-prefix` plugin keeps each tab label prefixed with its
one-based position inside its workspace. It reconciles labels at server startup
and whenever a tab is created, closed, renamed, or moved. Closing a tab before
the final position creates an unfocused blank replacement in the same position,
so the indexes of later tabs do not change. Closing the final tab does not create
a replacement. Exiting a tab's final shell with `exit` follows the same rule;
exiting one pane in a multi-pane tab does not create a tab.

Link it after setting up this repository on a new machine:

```sh
herdr plugin link ~/.config/herdr/tab-index-prefix
herdr plugin action invoke tab-index-prefix.reindex
```

## Restore plugins

Herdr's plugin registry and downloaded plugin directories are generated locally,
so reinstall the configured plugins after setting up this repository on a new
machine:

```sh
herdr plugin install -y qintmb/herdr-theme-picker
herdr plugin install -y paulbkim-dev/vim-herdr-navigation
```

Then reload the running server:

```sh
herdr server reload-config
```

Files such as `plugins.json`, `session.json`, `.plugins.lock`, logs, backups, and
the downloaded `plugins/` directory are runtime state and should not be tracked.

## Reproduce the setup on RHEL8

Run the following steps on the RHEL8 VM after installing Herdr. Make this
repository's `herdr/` directory available at `~/.config/herdr`, including
`config.toml`, the helper scripts, and `tab-index-prefix/`. Reinstall plugins on
the VM rather than copying `plugins.json`, which contains machine-specific
absolute paths.

The source Mac setup uses Herdr 0.9.0. Check the VM's version with
`herdr --version`; use the same version when reproducing the complete setup.
The local tab-index plugin and theme picker declare a minimum of 0.8.0, while
Vim navigation declares a minimum of 0.7.0.

### Plugins and dependencies

| Plugin | Purpose | Dependencies |
| --- | --- | --- |
| [vim-herdr-navigation](https://github.com/paulbkim-dev/vim-herdr-navigation) | Navigate Herdr panes and Vim/Neovim splits with `Ctrl+h/j/k/l`. | Bash, `jq`, editor integration below |
| [herdr-theme-picker](https://github.com/qintmb/herdr-theme-picker) | Select themes interactively; optional when keeping the configured colours. | Bash, `curl`, `fzf` |
| Local `tab-index-prefix` | Number tabs and preserve later tab positions when an earlier tab closes. | Bash, `jq`, `nc` with Unix-domain socket support (`-U`) |

Install the system dependencies:

```sh
sudo dnf install git bash curl jq nmap-ncat
sudo dnf install fzf
```

`fzf` requires a configured package repository that provides it, commonly EPEL.
If DNF cannot find it, use your VM's approved package source or install it using
the [upstream instructions](https://github.com/junegunn/fzf#installation).
The pane picker also requires `fzf`, `jq`, and `nc`.

Check that the commands are available and that `nc` supports `-U`:

```sh
command -v herdr bash curl git jq fzf nc
nc --help
```

### Adjust the helper scripts for Linux

Before launching Herdr with the copied configuration:

- `status-system-load.sh` calls `/opt/homebrew/bin/tmux-mem-cpu-load`. Install
  `tmux-mem-cpu-load` on the VM and replace that absolute path with its Linux
  location. Alternatively, remove the `tab_bar_right` entry from the `[ui]`
  section of `config.toml` to disable this status display.
- `pane-picker.sh` overrides `PATH` with Mac-oriented directories. Remove its
  `PATH=...` assignment and `export PATH` line to inherit the VM's normal path.
  Ensure that path includes `fzf`, `jq`, and `nc`, especially when tools are
  installed under `~/.local/bin`.

### Install and activate the plugins

```sh
herdr plugin install paulbkim-dev/vim-herdr-navigation
herdr plugin install qintmb/herdr-theme-picker
herdr plugin link ~/.config/herdr/tab-index-prefix
```

The GitHub installs show a review prompt; add `-y` for non-interactive setup.
Start Herdr with `herdr`, then run these commands from a pane:

```sh
herdr server reload-config
herdr plugin action invoke tab-index-prefix.reindex
herdr plugin list
```

The repository's `config.toml` already binds `Ctrl+h/j/k/l` to navigation and
`Ctrl+b`, then `t` to the theme picker. If you skip the optional theme picker,
remove its `[[keys.command]]` block. The configured colours remain available.

### Enable the editor side of navigation

For Neovim, also make the repository's Neovim configuration available on the VM,
including `~/.config/nvim/lua/plugins/herdr-navigation.lua`. In Neovim, run:

```vim
:Lazy sync
```

Restart Neovim inside a Herdr pane. The existing Lazy specification installs the
same navigation repository and loads `editor/nvim.lua`; both the Herdr plugin
and this editor integration are needed for navigation across editor boundaries.

For Vim instead, source `editor/vim.vim` from the installed navigation plugin
in your `~/.vimrc`, using the actual plugin checkout path on the VM. See the
[navigation plugin instructions](https://github.com/paulbkim-dev/vim-herdr-navigation#2-wire-up-your-editor).

### Verify the setup

- Confirm `herdr plugin list` shows the installed plugins enabled.
- Open multiple Herdr panes and Neovim splits, then try `Ctrl+h/j/k/l` across
  both kinds of boundary.
- Press `Ctrl+b`, then `t` to open the theme picker if installed.
- Create and close tabs to check numbering and blank replacement behaviour.
- Press `Ctrl+b`, then `f` to check the pane picker.

These are reproduction instructions based on the local configuration; the
RHEL8 installation has not been validated by this documentation update.
