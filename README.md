# GitHub Folder Sync

Home Assistant custom integration for syncing the Home Assistant config folder to GitHub.

## Features

- GitHub personal access token login
- Create a new repository or use an existing one
- Sync the Home Assistant config folder into GitHub
- Auto-generate a Home Assistant-friendly `.gitignore`
- Let you add extra ignore patterns from setup
- Manual sync button in Home Assistant
- Scheduled syncs at a configurable interval
- Ignore patterns for files you do not want uploaded

## Notes

- This is not a zip-backup integration.
- Files are synced individually as repository contents.
- The Home Assistant config folder is used automatically.
- A managed `.gitignore` is created with Home Assistant defaults and your extra patterns.
- Keep the repository private if the config contains sensitive data.
- The uploaded base was adapted into this folder-sync implementation.
