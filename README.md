# GitHub Folder Sync

Home Assistant custom integration for syncing a chosen local folder with a GitHub repository.

## Features

- GitHub personal access token login
- Create a new repository or use an existing one
- Sync a local folder into GitHub while preserving folder structure
- Manual sync button in Home Assistant
- Scheduled syncs at a configurable interval
- Ignore patterns for files you do not want uploaded

## Notes

- This is not a zip-backup integration.
- Files are synced individually as repository contents.
- Keep the repository private if the folder contains sensitive data.
- The uploaded base was adapted into this folder-sync implementation.
