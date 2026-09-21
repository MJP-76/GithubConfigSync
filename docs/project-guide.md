# Project guide

A summary of [PROJECT.md](https://github.com/MJP-76/GithubConfigSync/blob/main/PROJECT.md) — the single source of truth for
status, architecture, security, and workflow.

## Current status

<!-- VERSION:START -->
- Integration version: `1.6.1`
- Add-on version: `1.6.1`
- Channel: `stable`
- Release tag: `v1.6.1`
<!-- VERSION:END -->

- **Repo:** `MJP-76/GithubConfigSync` — single version on `main` (the `-dev` repo is decommissioned)
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

- Tokens are **never logged** and are always masked in the web UI and API
  responses; they are persisted only via the standard Supervisor options
  mechanism (plaintext on host storage), which the add-on cannot change.
- Sensitive-file scanning **blocks** uploads (since v1.5.0) and writes
  `SECURITY_UPLOAD_WARNINGS.md`.
- `_local_path_for` validates resolved paths stay inside the allowed root map.
- Diagnostics redaction strips `ghp_`, `github_pat_`, `gho_`, bearer tokens,
  key-value secrets, and credential URLs.

## Release workflow

1. Update code.
2. Bump the single version in `config.yaml` (source of truth).
3. Bump version in `manifest.json` and `hacs.json`.
4. Update the changelog (last 5 releases at the top).
5. Commit and push to `main` (single-version repo; the `-dev` repo is
   decommissioned).
6. Tag `vX.Y.Z` and create the GitHub release (pre-release until confirmed).

The full [PROJECT.md](https://github.com/MJP-76/GithubConfigSync/blob/main/PROJECT.md) contains the milestone history and the
per-tag release checklist.