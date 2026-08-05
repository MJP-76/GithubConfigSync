# Github Config Sync

[![Home Assistant][badge-home-assistant]][home-assistant]
[![Hassfest][badge-hassfest]][workflow-hassfest]
[![CI][badge-ci]][workflow-ci]
[![Release][badge-release]][releases]
[![Built with AI][badge-built-with-ai]][built-with-ai]

Home Assistant **add-on** for syncing your config folder to GitHub. This is a config sync tool, not a backup tool.

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

> **This is a Home Assistant add-on, not a HACS integration.** Install it from the Add-on Store.

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

- This is not a zip-backup tool — files are synced individually as repository contents.
- The Home Assistant config folder is used automatically.
- A managed `.gitignore` is created with HA defaults and your extra patterns.
- Keep the repository private if your config contains sensitive data.
- After a release, Home Assistant may need a rebuild/reinstall to pick up UI changes from the add-on image.

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
[home-assistant]: https://www.home-assistant.io/
[badge-hassfest]: https://img.shields.io/github/actions/workflow/status/MJP-76/GithubConfigSync/hassfest.yml?branch=main&label=Hassfest
[workflow-hassfest]: https://github.com/MJP-76/GithubConfigSync/actions/workflows/hassfest.yml
[badge-ci]: https://github.com/MJP-76/GithubConfigSync/actions/workflows/ci.yml/badge.svg
[workflow-ci]: https://github.com/MJP-76/GithubConfigSync/actions/workflows/ci.yml
[badge-release]: https://img.shields.io/github/v/release/MJP-76/GithubConfigSync?style=flat&label=Release
[releases]: https://github.com/MJP-76/GithubConfigSync/releases
[badge-built-with-ai]: https://img.shields.io/badge/Built%20with-AI-black?logo=openai&logoColor=white
[built-with-ai]: https://openai.com
