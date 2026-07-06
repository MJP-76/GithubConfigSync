# Github Config Sync
[![Validate](https://github.com/MJP-76/GithubConfigSync/actions/workflows/validate.yml/badge.svg)](https://github.com/MJP-76/GithubConfigSync/actions/workflows/validate.yml)
[![HACS](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

Home Assistant custom integration for syncing the Home Assistant config folder to GitHub.

## Version Tracker

<!-- VERSION:START -->
- Integration version: `0.0.22`
- Add-on version: `0.1.5`
- Channel: `stable`
- Release tag: `v0.0.22`
<!-- VERSION:END -->

To sync versions across integration/add-on/runtime/docs automatically:

```bash
python3 scripts/sync_versions.py --integration 0.0.20 --addon 0.1.3 --channel stable
```

For a dev release:

```bash
python3 scripts/sync_versions.py --integration 0.0.20 --addon 0.1.3 --channel dev
```

## Home Assistant Add-on (Web UI)

This repository now also includes a containerized Home Assistant add-on with ingress UI under:

`addons/github-config-sync/`

Add-on repository metadata is provided via `repository.yaml` so it can be added directly in Home Assistant Add-on Store.

## Installation (Add-on)

1. In Home Assistant, open **Settings → Add-ons → Add-on Store → Repositories**.
2. Add this repository URL: `https://github.com/MJP-76/GithubConfigSync`.
3. Install **Github Config Sync** add-on and start it.
4. Open the add-on web UI (ingress), configure repository settings, and complete GitHub Device Flow login.

## Installation (HACS)

1. Open HACS in Home Assistant.
2. Add `MJP-76/GithubConfigSync` as a custom repository (category: Integration).
3. Install **Github Config Sync** and restart Home Assistant.

## Features

- GitHub OAuth Device Flow login (approve on github.com)
- Create a new repository or use an existing one
- Sync the Home Assistant config folder into GitHub
- Auto-generate a Home Assistant-friendly `.gitignore`
- Let you add extra ignore patterns from setup
- Manual sync button in Home Assistant
- Scheduled syncs every 24 hours by default
- Customizable sync start time and repeat interval
- Ignore patterns for files you do not want uploaded

## Notes

- This is not a zip-backup integration.
- Files are synced individually as repository contents.
- The Home Assistant config folder is used automatically.
- A managed `.gitignore` is created with Home Assistant defaults and your extra patterns.
- Keep the repository private if the config contains sensitive data.
- The uploaded base was adapted into this folder-sync implementation.
- If `GITHUB_OAUTH_CLIENT_ID` is set in `custom_components/github_config_sync/const.py`, the flow uses it and skips asking for client ID.
