# Github Config Sync Add-on

Containerized Home Assistant add-on with an ingress web UI for GitHub sync operations.

## Version Tracker

<!-- VERSION:START -->
- Integration version: `0.0.25`
- Add-on version: `0.0.25`
- Channel: `stable`
- Release tag: `v0.0.25`
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

## Runbook

### Dry run

1. Configure repository, branch, and device-flow credentials.
2. Keep `dry_run` enabled.
3. Start a sync from the UI.
4. Confirm the scan summary and dry-run result match expectations.

### Live run

1. Confirm the repository is reachable with the saved token.
2. Disable `dry_run`.
3. Start a sync from the UI.
4. Confirm the probe succeeds and the final result reports upserts, deletes, and skips.

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
4. Click **Start Device Login**, approve on GitHub, then **Complete Device Login**.
5. Save settings and click **Run Sync Now**.

## Notes

- `dry_run` is enabled by default to avoid accidental pushes.
- This add-on is designed as a polished operator UI layer and can be wired to deeper sync logic incrementally.
