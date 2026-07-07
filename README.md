# Github Config Sync
[![CI](https://github.com/MJP-76/GithubConfigSync/actions/workflows/validate.yml/badge.svg)](https://github.com/MJP-76/GithubConfigSync/actions/workflows/validate.yml)
[![HASSfest](https://img.shields.io/badge/HASSfest-validated-success.svg)](https://developers.home-assistant.io/docs/creating_integration_manifest/)
[![HACS](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-Compatible-03a9f4.svg)](https://www.home-assistant.io/)
[![HA Ready](https://img.shields.io/badge/Home%20Assistant-Ready-03a9f4.svg)](https://www.home-assistant.io/)
[![Python](https://img.shields.io/badge/Python-3.12+-3776AB.svg)](https://www.python.org/)
[![Manifest](https://img.shields.io/badge/Manifest-validated-success.svg)](https://developers.home-assistant.io/docs/creating_integration_manifest/)
[![Release](https://img.shields.io/github/v/tag/MJP-76/GithubConfigSync?label=release)](https://github.com/MJP-76/GithubConfigSync/releases)

Home Assistant custom integration for syncing the Home Assistant config folder to GitHub. This is a config sync tool, not a backup tool. Use caution with any two-way sync or other tools that can also write to the Home Assistant config tree, because they can cause local config loss or unexpected deletions.

This documentation and code were drafted with AI assistance and then reviewed/edited by the maintainer.

## Support me

If you find this project useful, and would like to help support its continued development, you can do so here:

[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-FFDD00?style=for-the-badge&logo=buymeacoffee&logoColor=000000)](https://www.buymeacoffee.com/mjp76)
[![Ko-fi](https://img.shields.io/badge/Ko--fi-F16061?style=for-the-badge&logo=ko-fi&logoColor=ffffff)](https://ko-fi.com/mjp76)
[![Octopus Energy — you get £50, I get £50](https://img.shields.io/badge/Octopus%20Energy-%E2%80%94%20you%20get%20%C2%A350%2C%20I%20get%20%C2%A350-14294A?style=for-the-badge&logo=octopus-energy&logoColor=ffffff)](https://share.octopus.energy/iron-moose-196)

## Version Tracker

<!-- VERSION:START -->
- Integration version: `0.2.33`
- Add-on version: `0.2.33`
- Channel: `stable`
- Release tag: `v0.2.33`
<!-- VERSION:END -->

To sync versions across integration/app/runtime/docs automatically:

```bash
python3 scripts/sync_versions.py --integration 0.0.20 --addon 0.1.3 --channel stable
```

For a dev release:

```bash
python3 scripts/sync_versions.py --integration 0.0.20 --addon 0.1.3 --channel dev
```

## Home Assistant App (Web UI)

This repository now also includes a containerized Home Assistant app with ingress UI under:

`addons/github-config-sync/`

App repository metadata is provided via `repository.yaml` so it can be added directly in Home Assistant Add-on Store.

## Sync defaults

- Runs once a day by default.
- Keeps 7 GitHub version snapshots by default.
- Both values are configurable in the app UI.

## Architecture

- The custom integration handles Home Assistant entities, config flow, and operator actions.
- The app provides the ingress web UI and the sync runtime API.
- Sync planning is hash-based: the app scans `/config`, diffs against the last saved hash index, and classifies files as added, changed, or removed.
- AppDaemon configs and apps under `/addon_configs/` are included in the normal sync scan.
- The mount-point checklist lets you include or exclude standard Home Assistant folders, and the recommended .gitignore keeps the ignore list aligned.
- Dry runs do not touch GitHub; live runs probe the repository first, then upsert and delete files through the GitHub Contents API. Remote deletes never remove local files.
- Live runs also write versioned snapshots under `versions/<timestamp>/...` and keep the most recent 7 by default.
- State, logs, device-flow data, and the last hash index live in `/data`.
- The app exposes a stable local API contract via `/api/health`, `/api/status`, `/api/sync`, and `/api/diagnostics`.
- The generated `.gitignore` includes the common Home Assistant guidance entries such as `secrets.yaml`, `ip_bans.yaml`, `known_devices.yaml`, `.storage/`, and `.cloud/`, while still honoring any local user additions.
- After a release, Home Assistant may need a rebuild/reinstall to pick up UI changes from the app image.

## Runbook

### Dry run

1. Open the app UI and confirm `github_repository`, `github_branch`, and `dry_run=true`.
2. Start or complete GitHub device login if a token is not already present.
3. Run a sync and review the scan summary and dry-run result in the status panel.
4. Confirm the result shows the expected upsert/delete counts without changing GitHub contents.

### Live run

1. Verify the target repository exists and is accessible with the saved token.
2. Confirm the branch name is correct for the target repo.
3. Set `dry_run=false` in the app settings.
4. Run a sync, or use **Clean Upload** to force a full re-upload plus cleanup of remote extras.
5. Confirm the repository probe succeeds before the write phase.
6. Review the status panel and logs for the final upsert/delete/skip counts.

### Diagnostics bundle

1. Open the app UI.
2. Click **Download Diagnostics**.
3. Share the resulting JSON with support or use it to compare config, status, and sanitized logs.

## Release checklist

Before tagging a release:

1. Bump the integration/app versions as needed.
2. Run the repository validation workflow and the app test suite.
3. Confirm the docs and plan are updated and the tracker matches the shipped state.
4. Create the tag and publish the release.
5. Update the changelog and migration notes.

## Installation (App)

1. In Home Assistant, open **Settings → Add-ons → Add-on Store → Repositories**.
2. Add this repository URL: `https://github.com/MJP-76/GithubConfigSync`.
3. Install **Github Config Sync** and start it.
4. Open the app web UI (ingress), configure repository settings, and complete GitHub Device Flow login.

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
- HACS repository metadata is currently aligned with the integration manifest: repository name, URL, maintainer, and category wiring are present.
- New repository creation now falls back to a humanized default name/description when those fields are left blank.
- New release includes the repo-create blank-field defaults and the sync stability fixes from the prior commits.

## Sync verification

- **Dry run**: use `dry_run: true` first to confirm the scan is picking up added, changed, and removed files without pushing anything.
- **Live run**: switch `dry_run` to `false` only after the dry-run summary looks correct, then confirm the repository probe succeeds and the run reports upserts/deletes as expected.
- **Recovery check**: if a file is missing locally during a live run, it is counted as skipped rather than forcing a bad write.
