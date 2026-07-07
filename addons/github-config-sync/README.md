# Github Config Sync Add-on
[![CI](https://github.com/MJP-76/GithubConfigSync/actions/workflows/validate.yml/badge.svg)](https://github.com/MJP-76/GithubConfigSync/actions/workflows/validate.yml)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-Add--on-03a9f4.svg)](https://www.home-assistant.io/)
[![HA Ready](https://img.shields.io/badge/Home%20Assistant-Ready-03a9f4.svg)](https://www.home-assistant.io/)
[![Python](https://img.shields.io/badge/Python-3.12+-3776AB.svg)](https://www.python.org/)
[![HASSfest](https://img.shields.io/badge/HASSfest-validated-success.svg)](https://developers.home-assistant.io/docs/add-ons/)
[![Release](https://img.shields.io/github/v/tag/MJP-76/GithubConfigSync?label=release)](https://github.com/MJP-76/GithubConfigSync/releases)

Containerized Home Assistant add-on with an ingress web UI for GitHub sync operations.

> [!IMPORTANT]
> [Support me](../SUPPORT.md)

## Version Tracker

<!-- VERSION:START -->
- Integration version: `0.2.6`
- Add-on version: `0.2.6`
- Channel: `stable`
- Release tag: `v0.2.6`
<!-- VERSION:END -->

## What it provides

- Ingress-ready web UI (`/api` + browser dashboard)
- Config persistence in `/data`
- GitHub repository connectivity checks
- Hash-based change detection (added/changed/removed files)
- Manual dry-run sync trigger for safe validation
- Runtime status and log tail in the UI

## Architecture

- `server.py` is the add-on API surface and UI backend.
- `sync/engine.py` computes the plan from the current `/config` tree and the saved hash index.
- `dry_run=true` stops after planning and returns the counts that would be applied.
- `dry_run=false` probes the GitHub repository first, then performs upserts and deletes with the GitHub Contents API.
- Runtime state is persisted in `/data/state.json`, `/data/hash_index.json`, `/data/device_flow.json`, and `/data/sync.log`.
- The stable local API contract is `/api/health`, `/api/status`, `/api/sync`, and `/api/diagnostics`.
- After a release, Home Assistant may need a rebuild/reinstall to pick up UI changes from the add-on image.

## Runbook

### Dry run

1. Configure repository, branch, and device-flow credentials.
2. Keep `dry_run` enabled.
3. Start a sync from the UI.
4. Confirm the scan summary and dry-run result match expectations.

### Live run

1. Confirm the repository is reachable with the saved token.
2. Confirm the branch name is correct for the target repo.
3. Disable `dry_run`.
4. Start a sync from the UI, or use **Clean Upload** to force a full re-upload plus cleanup of remote extras.
5. Confirm the probe succeeds and the final result reports upserts, deletes, and skips.

### Diagnostics bundle

1. Open the UI and click **Download Diagnostics**.
2. Share the JSON bundle for troubleshooting.
3. The bundle includes masked options, current state, auth diagnostics, and a sanitized log tail.

## Release checklist

1. Bump the add-on version and sync the version tracker.
2. Run the add-on unit tests.
3. Update the changelog and migration notes.
4. Publish the release tag.

## First run

1. Add this repository as a Home Assistant add-on repository.
2. Install **Github Config Sync** add-on.
3. Open the add-on web UI and set:
   - `github_repository` (`owner/repo`)
   - `github_branch`
   - `github_client_id` (defaults to the built-in app ID)
4. Click **Start Device Login**, approve on GitHub, and wait for the login to complete automatically.
5. Save settings and click **Run Sync Now**.
6. Private repositories are supported, but the token must have access to the selected repo and branch.

## Notes

- `dry_run` is enabled by default to avoid accidental pushes.
- This add-on is designed as a polished operator UI layer and can be wired to deeper sync logic incrementally.

## Verification notes

- Start with a dry run and confirm the API summary matches the expected file changes.
- For a live run, disable `dry_run` only after the repository probe passes and the GitHub token has repo write access.
- Missing local files during an upsert are skipped; missing remote files during deletes are skipped as well.

## Support me

See [SUPPORT.md](../SUPPORT.md) for support links.
