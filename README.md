# Github Config Sync
[![Validate](https://github.com/MJP-76/GithubConfigSync/actions/workflows/validate.yml/badge.svg)](https://github.com/MJP-76/GithubConfigSync/actions/workflows/validate.yml)
[![HACS](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

Home Assistant custom integration for syncing the Home Assistant config folder to GitHub.

## Installation (HACS)

1. Open HACS in Home Assistant.
2. Add `MJP-76/GithubConfigSync` as a custom repository (category: Integration).
3. Install **Github Config Sync** and restart Home Assistant.

## Features

- GitHub personal access token login
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
