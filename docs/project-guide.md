# Project guide

A summary of [PROJECT.md](https://github.com/MJP-76/GithubConfigSync/blob/main/PROJECT.md) — the single source of truth for
status, architecture, security, and workflow.

## Current status

<!-- VERSION:START -->
- Integration version: `1.7.12`
- Add-on version: `1.7.12`
- Channel: `stable`
- Release tag: `v1.7.12`
<!-- VERSION:END -->

- **Repo:** `MJP-76/GithubConfigSync` — single version on `main`
- **Add-on path:** `addons/github-config-sync/`
- **Integration path:** `custom_components/github_config_sync/`
- **App source:** `addons/github-config-sync/rootfs/app/`
- **Version source of truth:** `config.yaml` (auto-read at startup)

## Architecture

1. **Integration** (`custom_components/github_config_sync/`) — a redirect: its
   config flow aborts with `addon_only` to send the user to the add-on, and it
   has no entity platforms.
2. **Add-on** (`addons/github-config-sync/`) — ingress web UI running a Flask
   server that handles OAuth Device Flow, repository management (list, create,
   adopt), config sync (upload, clean-upload, clean-repo), and settings
   persistence via the HA options API.
3. **Sync engine** (`rootfs/app/sync/`) — core logic in `engine.py` (planning,
   diffing, upload, clean, layout migration), `github_client.py` (GitHub API
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

Described once, in
[AGENTS.md](https://github.com/MJP-76/GithubConfigSync/blob/main/AGENTS.md) — the ordered steps, the changelog rules and the
per-tag checklist all live there, with the reasoning behind each rule.

The full [PROJECT.md](https://github.com/MJP-76/GithubConfigSync/blob/main/PROJECT.md) contains the milestone history,
architecture and product decisions.