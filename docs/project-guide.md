# Project guide

A summary of [PROJECT.md](https://github.com/MJP-76/GithubConfigSync/blob/main/PROJECT.md) — the single source of truth for
status, architecture, security, and workflow.

## Current status

<!-- VERSION:START -->
- Integration version: `1.6.0`
- Add-on version: `1.6.0`
- Channel: `stable`
- Release tag: `v1.6.0`
<!-- VERSION:END -->

- **Repo:** `MJP-76/GithubConfigSync` — `main` = stable, `dev` = development
- **Add-on path:** `addons/github-config-sync/`
- **Integration path:** `custom_components/github_config_sync/`
- **App source:** `addons/github-config-sync/rootfs/app/`
- **Version source of truth:** `config.yaml` (auto-read at startup)

## Architecture

1. **Integration** (`custom_components/github_config_sync/`) — config flow for
   GitHub token setup, button entities for sync/clean actions, sensor entities
   for sync status.
2. **Add-on** (`addons/github-config-sync/`) — ingress web UI running a Flask
   server that handles OAuth Device Flow, repository management (list, create,
   adopt), config sync (upload, clean-upload, clean-repo), and settings
   persistence via the HA options API.
3. **Sync engine** (`rootfs/app/sync/`) — core logic in `engine.py` (planning,
   diffing, upload, clean, version snapshots), `github_client.py` (GitHub API
   with rate-limit retry/backoff), `models.py`, `errors.py`, and `hashing.py`
   (content hashing for change detection).

## Security

- Tokens are never persisted or logged in plaintext; the UI masks them.
- Sensitive-file scanning **blocks** uploads (since v1.5.0) and writes
  `SECURITY_UPLOAD_WARNINGS.md`.
- `_local_path_for` validates resolved paths stay inside the allowed root map.
- Diagnostics redaction strips `ghp_`, `github_pat_`, `gho_`, bearer tokens,
  key-value secrets, and credential URLs.

## Release workflow

1. Update code.
2. Bump version in `config.yaml` (single source of truth).
3. Bump version in `manifest.json` and `hacs.json`.
4. Update the changelog (last 5 releases at the top).
5. Commit and push to **dev**.
6. When stable, push to **main** and create the GitHub release.

The full [PROJECT.md](https://github.com/MJP-76/GithubConfigSync/blob/main/PROJECT.md) contains the milestone history and the
per-tag release checklist.