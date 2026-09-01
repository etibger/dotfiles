# Herdr configuration

This directory contains the portable Herdr configuration and helper scripts.

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
