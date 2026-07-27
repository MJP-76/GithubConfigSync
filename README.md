# Github Config Sync

[![Home Assistant][badge-home-assistant]][home-assistant]
[![HACS][badge-hacs]][hacs]
[![CI][badge-ci]][workflow-ci]
[![Hassfest][badge-hassfest]][workflow-hassfest]
[![Release][badge-release]][releases]
![Status][badge-status]
[![Built with AI][badge-ai]](https://openai.com)

Home Assistant integration and add-on for syncing your config folder to GitHub. This is a config sync tool, not a backup tool.

**Private repositories are strongly recommended.** Use caution with public repos and any two-way sync tools that also write to your Home Assistant config tree — they can cause local config loss or unexpected deletions.

## Support me

If you find this project useful, and would like to help support its continued development, you can do so here:

[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-FFDD00?style=for-the-badge&logo=buymeacoffee&logoColor=000000)](https://www.buymeacoffee.com/mjp76)
[![Ko-fi](https://img.shields.io/badge/Ko--fi-F16061?style=for-the-badge&logo=ko-fi&logoColor=ffffff)](https://ko-fi.com/mjp76)
[![Octopus Energy — you get £50, I get £50](https://img.shields.io/badge/Octopus%20Energy-%E2%80%94%20you%20get%20%C2%A350%2C%20I%20get%20%C2%A350-14294A?style=for-the-badge&logo=octopus-energy&logoColor=ffffff)](https://share.octopus.energy/iron-moose-196)

## Features

- GitHub OAuth Device Flow login (approve on github.com)
- Create a new repository or use an existing one
- Sync your Home Assistant config folder to GitHub
- Auto-generate a Home Assistant-friendly `.gitignore`
- Customizable ignore patterns
- Manual sync button in Home Assistant
- Scheduled syncs (day-of-week + time-of-day selection)
- Optional dated GitHub release creation before each sync
- Clean Upload — force full re-upload and remove remote extras
- Clean Repo — wipe remote repo and restore starter files in one step
- Repository picker with safety checks to avoid accidental overwrites
- Sensitive-file scanning and reporting

## Installation

[![Add Integration](https://my.home-assistant.io/badges/integration.svg)](https://my.home-assistant.io/redirect/integration?domain=github_config_sync)

### HACS (recommended)

1. Open HACS in Home Assistant.
2. Add `https://github.com/MJP-76/GithubConfigSync` as a custom repository (category: Integration).
3. Install **Github Config Sync** and restart Home Assistant.
4. Go to **Settings → Devices & Services → Add Integration → Github Config Sync** and configure.

### Add-on Store

1. In Home Assistant, open **Settings → Add-ons → Add-on Store → Repositories**.
2. Add this repository URL: `https://github.com/MJP-76/GithubConfigSync`.
3. Install **Github Config Sync** and start it.
4. Open the app web UI (ingress), configure repository settings, and complete GitHub Device Flow login.

## Getting Started

1. Open the app UI from the Add-on page.
2. Complete GitHub Device Flow login.
3. Pick an existing repository or create a new one.
4. Run a dry run first to confirm the scan looks correct.
5. Switch to a live run when ready.

## Default Ignore List

The following are excluded from sync by default:

- **HA runtime:** `.storage`, `.cloud`, `tts`, `.ha_run.lock`, `home-assistant.log`, `home-assistant.log.*`, `home-assistant_v2.db`, `home-assistant_v2.db-*`, `secrets.yaml`, `ip_bans.yaml`, `known_devices.yaml`
- **Databases:** `*.db`, `*.sqlite`, `*.sqlite3`
- **Dev/cache:** `.git`, `.cache`, `.venv`, `.vscode`, `.idea`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `__pycache__`, `.yaml_fix_backups`, `.yaml_fix_backups/*`
- **Temp/junk:** `*.tmp`, `*.swp`, `*.pyc`, `*.log`, `*.smbdelete*`, `.DS_Store`, `Thumbs.db`, `.ha_fix_yaml.py`

You can add extra patterns in the app UI. Live uploads also write a root `SECURITY_UPLOAD_WARNINGS.md` file when suspicious files are skipped.

## Notes

- This is not a zip-backup integration — files are synced individually as repository contents.
- The Home Assistant config folder is used automatically.
- A managed `.gitignore` is created with HA defaults and your extra patterns.
- Keep the repository private if your config contains sensitive data.
- After a release, Home Assistant may need a rebuild/reinstall to pick up UI changes from the add-on image.
- If `GITHUB_OAUTH_CLIENT_ID` is set in `custom_components/github_config_sync/const.py`, the flow uses it directly.

## Development Track

To use the dev branch, add the dev repository URL in **Settings → Add-ons → Add-on Store → Repositories**:

```
https://github.com/MJP-76/GithubConfigSync-dev
```

Development happens on the `dev` repo. When ready, changes are pushed to both repos.

## Documentation

- **[Project Guide](PROJECT.md)** — architecture, security, milestones, and release workflow.
- **[Changelog](CHANGELOG.md)** — release history.

[badge-home-assistant]: https://img.shields.io/badge/Home%20Assistant-41BDF5?style=flat-square&logo=homeassistant&logoColor=white
[badge-hacs]: https://img.shields.io/badge/HACS-Custom-41BDF5.svg
[badge-ci]: https://github.com/MJP-76/GithubConfigSync/actions/workflows/validate.yml/badge.svg
[badge-hassfest]: https://img.shields.io/github/actions/workflow/status/MJP-76/GithubConfigSync/hassfest.yml?branch=main&label=Hassfest
[badge-release]: https://img.shields.io/github/v/tag/MJP-76/GithubConfigSync?label=release
[badge-status]: https://img.shields.io/badge/status-experimental-yellow
[home-assistant]: https://www.home-assistant.io/
[hacs]: https://github.com/hacs/integration
[workflow-ci]: https://github.com/MJP-76/GithubConfigSync/actions/workflows/validate.yml
[workflow-hassfest]: https://github.com/MJP-76/GithubConfigSync/actions/workflows/hassfest.yml
[releases]: https://github.com/MJP-76/GithubConfigSync/releases
