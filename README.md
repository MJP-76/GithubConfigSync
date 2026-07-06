# GitHub Config Sync

Home Assistant custom integration that backs up your Home Assistant config directory to GitHub as timestamped zip archives.

## Features

- GitHub token login
- Create a new repository or use an existing one
- Manual backup button in Home Assistant
- Scheduled backups at a configurable interval
- Ignore patterns for files you do not want uploaded

## Notes

- This uses a GitHub personal access token, not OAuth.
- Backups are stored as versioned zip files in the repository.
- Keep the repository private if the archive contains sensitive config data.
