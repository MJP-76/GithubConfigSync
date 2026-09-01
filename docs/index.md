# Github Config Sync

[![Home Assistant][badge-home-assistant]][home-assistant]
[![Hassfest][badge-hassfest]][workflow-hassfest]
[![CI][badge-ci]][workflow-ci]
[![Release][badge-release]][releases]
[![Built with AI][badge-built-with-ai]][built-with-ai]

A Home Assistant **add-on** for syncing your config folder to GitHub. This is
a **config sync tool, not a backup tool**.

!!! danger "Keep the repository private"

    Private repositories are strongly recommended. Use caution with public
    repos and any two-way sync tools that also write to your Home Assistant
    config tree — they can cause local config loss or unexpected deletions.

## What this add-on does

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

## Where to go next

| Topic | Page |
|---|---|
| Install the add-on and first sync | [Installation](installation.md) |
| Ignore list, clean actions and safety notes | [Syncing](syncing.md) |
| Architecture, security and release workflow | [Project guide](project-guide.md) |
| Version history | [Changelog](changelog.md) |

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