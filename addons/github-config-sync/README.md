# Github Config Sync App
[![CI](https://github.com/MJP-76/GithubConfigSync/actions/workflows/validate.yml/badge.svg)](https://github.com/MJP-76/GithubConfigSync/actions/workflows/validate.yml)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-Add--on-03a9f4.svg)](https://www.home-assistant.io/)
[![HA Ready](https://img.shields.io/badge/Home%20Assistant-Ready-03a9f4.svg)](https://www.home-assistant.io/)
[![Python](https://img.shields.io/badge/Python-3.12+-3776AB.svg)](https://www.python.org/)
[![HASSfest](https://img.shields.io/badge/HASSfest-validated-success.svg)](https://developers.home-assistant.io/docs/add-ons/)
[![Release](https://img.shields.io/github/v/tag/MJP-76/GithubConfigSync?label=release)](https://github.com/MJP-76/GithubConfigSync/releases)

Containerized Home Assistant app with an ingress web UI for GitHub config sync operations. Release v1.0.0. This is a sync tool, not a backup tool.

Authentication supports GitHub Device Flow or a fine-grained PAT scoped to the single target repository.


<strong style="color:#ef4444">Danger Zone:</strong> <strong>private GitHub repositories are strongly recommended.</strong> Use caution with public repositories and with any two-way sync or other tools that can also write to the Home Assistant config tree, because they can cause local config loss or unexpected deletions. The developer and maintainer are not responsible for data loss.

This documentation and code were drafted with AI assistance and then reviewed/edited by the maintainer.

## Support me

If you find this project useful, and would like to help support its continued development, you can do so here:

[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-FFDD00?style=for-the-badge&logo=buymeacoffee&logoColor=000000)](https://www.buymeacoffee.com/mjp76)
[![Ko-fi](https://img.shields.io/badge/Ko--fi-F16061?style=for-the-badge&logo=ko-fi&logoColor=ffffff)](https://ko-fi.com/mjp76)
[![Octopus Energy — you get £50, I get £50](https://img.shields.io/badge/Octopus%20Energy-%E2%80%94%20you%20get%20%C2%A350%2C%20I%20get%20%C2%A350-14294A?style=for-the-badge&logo=octopus-energy&logoColor=ffffff)](https://share.octopus.energy/iron-moose-196)

## Version Tracker

<!-- VERSION:START -->
- Integration version: `1.0.0`
- Add-on version: `1.0.0`
- Channel: `stable`
- Release tag: `v1.0.0`
<!-- VERSION:END -->

## What it provides

- Ingress-ready web UI (`/api` + browser dashboard)
- Config persistence in `/data`
- GitHub repository connectivity checks
- Hash-based change detection (added/changed/removed files)
- Manual dry-run sync trigger for safe validation
- Runtime status and log tail in the UI

## Architecture

- `server.py` is the app API surface and UI backend.
- `sync/engine.py` computes the plan from the current `/config` tree and the saved hash index.
- AppDaemon configs and apps under `/addon_configs/` are included in the normal sync scan.
- The mount-point checklist lets you include or exclude standard Home Assistant folders, and the recommended .gitignore keeps the ignore list aligned.
- `dry_run=true` stops after planning and returns the counts that would be applied for manual actions. A separate scheduled-sync checkbox can override dry run for automated runs.
- `dry_run=false` probes the GitHub repository first, then performs upserts and deletes with the GitHub Contents API. Remote deletes never remove local files.
- **Clean Repo** always runs live, empties the remote repo with a fast git-tree reset, and restores the starter files in the same step.
- Repository creation uses the add-on flow and defaults to `ha-github-config-sync` with private visibility, with an optional public visibility choice.
- Live runs also write versioned snapshots under `versions/<timestamp>/...` (parallelized uploads) and keep the most recent 7 by default.
- Runtime state is persisted in `/data/state.json`, `/data/hash_index.json`, `/data/device_flow.json`, and `/data/sync.log`.
- The stable local API contract is `/api/health`, `/api/status`, `/api/sync`, and `/api/diagnostics`.
- Home Assistant shows the short repo-root changelog on the update page; the in-app UI reads the full changelog from the app folder.
- Stable and dev now use separate numeric lanes in the UI: stable `1.0.0` and dev `1.0.1`.
- Default ignores include:
  - `.storage`, `.cloud`, `.cache`, `.venv`, `.vscode`, `.idea`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `tts`, `__pycache__`, `.git`
  - `home-assistant.log`, `home-assistant.log.*`, `home-assistant_v2.db`, `home-assistant_v2.db-*`, `secrets.yaml`, `ip_bans.yaml`, `known_devices.yaml`, `.ha_run.lock`, `*.db`, `*.sqlite`, `*.sqlite3`, `*.tmp`, `*.swp`, `*.pyc`, `*.log`, `.yaml_fix_backups`, `.yaml_fix_backups/*`, `.ha_fix_yaml.py`, `.smbdelete*`, `.DS_Store`, `Thumbs.db`
- Live uploads also write a root `SECURITY_UPLOAD_WARNINGS.md` file when suspicious files are skipped.
- The add-on writes an internal repo marker on newly created repositories so clean actions and the repo picker only target safe repos.
- The repo-root changelog is updated on every pushed build/version so the HA update page stays current.

## Runbook

### Dry run

1. Configure repository, branch, and device-flow credentials.
2. Keep `dry_run` enabled.
3. Start a sync from the UI.
4. Confirm the scan summary and dry-run result match expectations.

### Defaults

1. Sync runs once a day by default.
2. Version snapshots keep the last 7 copies by default.
3. Both settings are editable in the app UI.

### Live run

1. Confirm the repository is reachable with the saved token.
2. Confirm the branch name is correct for the target repo.
3. Disable `dry_run`.
4. Start a sync from the UI, or use **Clean Upload** to force a full re-upload plus cleanup of remote extras. **Clean Repo** empties the remote repo with a fast git-tree reset and restores the starter files in one live step. If scheduled sync should ignore dry run, enable the scheduled override checkbox first.
5. Confirm the probe succeeds and the final result reports upserts, deletes, and skips.

### Diagnostics bundle

1. Open the UI and click **Download Diagnostics**.
2. Share the JSON bundle for troubleshooting.
3. The bundle includes masked options, current state, auth diagnostics, and a sanitized log tail.

## Release checklist

1. Bump the app version and sync the version tracker.
2. Run the app unit tests.
3. Update the changelog and migration notes.
4. Publish the release tag.

## First run

1. Add this repository as a Home Assistant repository.
2. Install **Github Config Sync**.
3. Open the app web UI and set:
   - `github_repository` (`owner/repo`)
   - `github_branch`
   - `github_client_id` (defaults to the built-in app ID)
4. Click **Start Device Login**, approve on GitHub, and wait for the login to complete automatically.
5. Save settings and click **Run Sync Now**.
6. Private repositories are supported, but the token must have access to the selected repo and branch.

## Notes

- `dry_run` is enabled by default to avoid accidental pushes.
- This app is designed as a polished operator UI layer and can be wired to deeper sync logic incrementally.
- Security-focused safeguards are in place: private repositories are strongly recommended, sensitive-path filtering is active, and two-way sync warnings are visible. Follow-up work includes local API auth checks, path ancestry validation, and stronger diagnostics redaction.
- The latest release includes the danger-zone security updates in the changelog.
- The add-on repository metadata is minimal and valid for Home Assistant add-on store ingestion.
- Version snapshots now skip ignored directories like `.cache`, even inside release snapshots.
- New repository creation defaults blank name/description fields to a humanized repository name.
- This release carries the repo-create default behavior and the sync fixes from the last two commits.
- Release track split: `MJP-76/GithubConfigSync` publishes stable releases, and `MJP-76/GithubConfigSync-dev` publishes dev releases.
- Versioning rule: keep numeric `x.y.z` versions and use stable releases in the main repo with dev releases in the dev fork.

## Verification notes

- Start with a dry run and confirm the API summary matches the expected file changes.
- For a live run, disable `dry_run` only after the repository probe passes and the GitHub token has repo write access.
- Missing local files during an upsert are skipped; missing remote files during deletes are skipped as well.
