# Github Config Sync Add-on

Containerized Home Assistant add-on with an ingress web UI for GitHub sync operations.

## Version Tracker

<!-- VERSION:START -->
- Integration version: `0.0.21`
- Add-on version: `0.1.4`
- Channel: `stable`
- Release tag: `v0.0.21`
<!-- VERSION:END -->

## What it provides

- Ingress-ready web UI (`/api` + browser dashboard)
- Config persistence in `/data`
- GitHub repository connectivity checks
- Hash-based change detection (added/changed/removed files)
- Manual dry-run sync trigger for safe validation
- Runtime status and log tail in the UI

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
