# GitHub Config Sync

Home Assistant custom integration that syncs a chosen local folder to GitHub as tracked files.

## Features

- GitHub token login
- Create a new repository or use an existing one
- Manual sync button in Home Assistant
- Scheduled syncs at a configurable interval
- Optional GitHub-to-local sync direction
- Ignore patterns for files you do not want uploaded

## Notes

- This uses a GitHub personal access token, not OAuth.
- Files are synced individually, preserving folder structure in the repository.
- Keep the repository private if the folder contains sensitive config data.
