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
