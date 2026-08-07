# GitHub Config Sync — Project Guide

Single source of truth for project status, architecture, security, and workflow.

---

## Current Status

<!-- VERSION:START -->
- Integration version: `1.5.19`
- Add-on version: `1.5.19`
- Channel: `stable`
- Release tag: `v1.5.19`
<!-- VERSION:END -->
- **Last updated:** 2026-08-06
- **Repo:** `MJP-76/GithubConfigSync` (single repo, `main` = stable, `dev` = development)
- **Add-on path:** `addons/github-config-sync/`
- **Integration path:** `custom_components/github_config_sync/`
- **App source:** `addons/github-config-sync/rootfs/app/`
- **Version auto-read from:** `config.yaml` (single source of truth)

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

- [x] ~~Lock down local API endpoints with Supervisor/Ingress header checks~~ — `_require_ingress` decorator was implemented in v1.1.1 but **removed in v1.1.3** because HA reverse proxy strips the `X-Home-Assistant-Instance-ID` header. HA ingress URL token alone is sufficient authentication.
- [x] Revisit mount-point path resolution and path ancestry checks — `_local_path_for` validates resolved path stays within allowed root map before returning.
- [x] Tighten diagnostics redaction — `_sanitized_log_tail` applies `_redact_line` to strip `ghp_`, `github_pat_`, `gho_`, bearer tokens, key-value secrets, and credential URLs.
- [ ] Review whether any additional secret-scanning or blocklist patterns should be added later.

---

## Product Decisions

- Device Flow is the default auth path for both integration and add-on UX.
- Token/client ID should not be front-and-center for normal users.
- Repository selection is guided (picker/create) instead of manual-only typing.
- The Add-on Store is the supported distribution path; the legacy HACS integration is kept only to redirect installs to the add-on.
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
2. Bump version in `config.yaml` (single source of truth — `server.py` auto-reads it at startup).
3. Bump version in `manifest.json` and `hacs.json`.
4. Update changelog (last 5 releases at top).
5. Commit and push to dev.
6. When stable, push to main and create GitHub release.

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

### v1.1.1 — Security Hardening

- Security hardening: ingress header validation on mutating API endpoints
- Security hardening: path ancestry checks on filesystem operations
- Security hardening: diagnostics log redaction strips tokens, secrets, and URLs
- Consolidated project documentation into single PROJECT.md
- Rewrote README for user-facing clarity
- Added experimental status badge and My Home Assistant install button

### v1.1.2–v1.1.3 — Ingress Fix

- Removed `_require_ingress` — HA reverse proxy strips the header, making it unusable
- Device flow auth endpoints unblocked

### v1.2.0 — Background Scheduler

- Background scheduler with interval-based sync
- Scheduler re-reads settings each cycle

### v1.3.0–v1.3.3 — Scheduled Sync + UI Overhaul

- Day-of-week and time-of-day scheduled sync
- Optional dated release creation before each sync
- Auto-prune old sync releases
- Removed snapshot/versioning system (replaced by GitHub releases)
- Removed `sync_interval_minutes` and `manual_version_retention_days` options
- UI restructured: Installation and Usage card with collapsible sub-sections
- Safety & Security Recommendations section
- Diagnostics collapsible card

### v1.5.5 — Security & Hardening Release

- Sensitive file scanning now actually blocks uploads (was report-only)
- Auth guard on all POST endpoints (ingress token or github_token Bearer)
- Path safety via is_relative_to; retry on transient 5xx; pinned base image
- Legacy custom_components stripped to redirect-only
- Removed dead code (_require_ingress, _delete_remote_tree_except)

### v1.5.0–v1.5.4 — Security Hardening & Token Sync Fix

- Security fix: Sensitive file scanning now actually blocks uploads (was report-only)
- Token syncs from HA config entry to add-on via Supervisor API (fixes auth persistence)
- All include_* options default to false; added core.config_entries and .env to ignore patterns
- Whitelist/blacklist sync mode selection in separate web UI section
- SHA conflict retries with exponential backoff (3 attempts)
- Reset to Defaults button for .gitignore patterns
- Version auto-read from config.yaml via regex

### v1.4.0–v1.4.1 — Consolidated UI

- Consolidated all settings into Installation and Usage card (sub-sections 1–7)
- Auto-expand sections on first load when not configured, collapse once resolved
- Version auto-read from config.yaml — single source of truth
- SHA conflict retry with exponential backoff (3 attempts)
- Removed Troubleshooting options section
- Skeleton README reworded as HA add-on description

---

## Immediate Next Steps

- [ ] Keep this file aligned with the active release track.

---

## Release Checklist (Per Tag)

- [ ] Version bumped in `config.yaml`, `manifest.json`, `hacs.json`
- [ ] Changelog updated (last 5 releases at top)
- [ ] Validation/CI green
- [ ] Docs updated
- [ ] Committed and pushed to dev
- [ ] GitHub Release created
- [ ] This file updated
