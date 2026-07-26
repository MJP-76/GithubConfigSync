# GitHub Config Sync — Project Guide

Single source of truth for project status, architecture, security, and workflow.

---

## Current Status

- **Version:** `1.1.0`
- **Last updated:** 2026-07-26
- **Tracks:** Stable (`GithubConfigSync`) and Dev (`GithubConfigSync-dev`)
- **Add-on path:** `addons/github-config-sync/`
- **Integration path:** `custom_components/github_config_sync/`
- **App source:** `addons/github-config-sync/rootfs/app/`
- **Version script:** `scripts/sync_versions.py`

---

## Architecture

### Integration (`custom_components/github_config_sync/`)

Home Assistant integration that provides config flow for GitHub token setup, button entities for sync/clean actions, and sensor entities for sync status.

### Add-on (`addons/github-config-sync/`)

Home Assistant add-on with ingress web UI. Runs a Flask server that handles:

- OAuth Device Flow for GitHub authentication
- Repository management (list, create, adopt)
- Config sync (upload, clean-upload, clean-repo)
- Settings persistence via HA options API

### Sync Engine (`addons/github-config-sync/rootfs/app/sync/`)

- `engine.py` — Core sync logic: planning, diffing, upload, clean, version snapshots
- `github_client.py` — GitHub API client with rate-limit retry and backoff
- `models.py` — Data models for sync config and results
- `errors.py` — Sync error types
- `hashing.py` — File content hashing for change detection

---

## Security

- GitHub tokens are required for repository access and device-flow completion.
- The web UI masks stored tokens in API responses.
- Do not log tokens in plaintext.
- Prefer a private repository when syncing Home Assistant config data.
- If repository probing fails with an auth error, confirm the token has `repo` access.
- If device-flow login fails, restart authorization from the app UI and complete the browser step again.
- Keep `dry_run` enabled until the repository, token, and sync plan look correct.
- Review the app status panel and logs before enabling live syncs.

### Open security items

- [ ] Lock down local API endpoints with Supervisor/Ingress header checks and review diagnostics exposure.
- [ ] Revisit mount-point path resolution and path ancestry checks for any user-controlled filesystem inputs.
- [ ] Tighten diagnostics redaction to strip auth headers, URLs, and token-shaped secrets before export.
- [ ] Review whether any additional secret-scanning or blocklist patterns should be added later.

---

## Product Decisions

- Device Flow is the default auth path for both integration and add-on UX.
- Token/client ID should not be front-and-center for normal users.
- Repository selection is guided (picker/create) instead of manual-only typing.
- Both Hassfest and HACS validation are in place while integration distribution continues.
- Stable / dev version lines are explicit so the repo ships the right track from the right repository.

---

## Default Ignore List

`.storage`, `.cloud`, `.cache`, `.venv`, `.vscode`, `.idea`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `tts`, `__pycache__`, `.git`, `home-assistant.log`, `home-assistant.log.*`, `home-assistant_v2.db`, `home-assistant_v2.db-*`, `secrets.yaml`, `ip_bans.yaml`, `known_devices.yaml`, `.ha_run.lock`, `*.db`, `*.sqlite`, `*.sqlite3`, `*.tmp`, `*.swp`, `*.pyc`, `*.log`, `.yaml_fix_backups`, `.yaml_fix_backups/*`, `.ha_fix_yaml.py`, `.smbdelete*`, `.DS_Store`, `Thumbs.db`

---

## Changelog Rules

- The HA update page uses the short repo-root changelog.
- The in-app UI uses the full app changelog.
- Update the repo-root changelog on every pushed build/version so the HA update page stays current.
- Last 5 releases at the top with full details; older releases below a divider.

---

## Release Workflow

1. Update code.
2. Bump versions in `config.yaml`, `manifest.json`, `server.py`, `hacs.json`.
3. Update changelog (last 5 releases at top).
4. Run existing tests.
5. Commit and push to dev.
6. Create GitHub release.
7. When stable, push to stable repo and create release.

---

## Cross-Device Handoff

1. Pull the latest from the active branch.
2. Read this file for current status and architecture.
3. Check the latest release tag on GitHub.
4. Continue work and keep this file updated.

---

## Completed Milestones

### Foundation (v0.1.0–v0.1.2)

- Custom integration scaffold with config flow + token handling
- HACS metadata and validation workflow
- GitHub release/tag pipeline
- Add-on scaffold with ingress UI
- Hash-based changed-file detection
- Real GitHub upsert/delete sync path

### Security + Auth (v0.1.3–v0.1.4)

- Token never persisted/logged in plaintext
- OAuth path hardened with clear fallback/error handling
- Integration ↔ add-on stable local API contract
- Diagnostics export bundle

### Quality + Release (v0.1.5–v0.1.13)

- Unit tests for sync engine + API + config validation
- CI with integration checks + add-on checks + tests
- Version tracker synced across integration, add-on, runtime, and docs
- Auto-select newly created repository in the repo picker
- Clean upload preserves version snapshots and app README

### v1.0.x — Production

- Stuck upload progress fix
- Repository adoption flow
- Managed repo picker
- Rate-limit retry with backoff
- `hacs_frontend` and `node_modules` ignore patterns
- Repo marker support for clean actions
- Default ignore rules for HA runtime files
- Sensitive-file scanning and reporting

### v1.1.0 — Current

- Managed repos always verified against live GitHub marker file
- Stale cache no longer keeps unmanaged repos in the list
- Clean-repo no longer blocked by missing markers
- Cancel support for clean-repo
- Atomic-operation warnings on Clean Upload/Repo dialogs
- UI loads live repos on init instead of stale cache
- Fixed `_repo_safety_state()` missing return values
- Updated changelog format

---

## Immediate Next Steps

- [ ] Normalize version tracker across stable and dev release lines.
- [ ] Close remaining security hardening follow-ups.
- [ ] Keep this file aligned with the active release track.

---

## Release Checklist (Per Tag)

- [ ] Version bumped (integration + add-on)
- [ ] Run `python3 scripts/sync_versions.py` if applicable
- [ ] Validation/CI green
- [ ] Docs updated
- [ ] Tag created and pushed
- [ ] GitHub Release created
- [ ] This file updated
