# Changelog

## Unreleased

- Preparing the v0.2.25 release bump.

- Fixed GitHub OAuth client helper loading so Device Flow start completes reliably.
- Retried version snapshot writes on stale SHA conflicts so GitHub 409s no longer abort releases.

## 0.2.21

- Added the remote-delete/local-file caution to the docs and app page.
- Clarified that clean upload deletes only remote GitHub content.

## 0.2.20

- Updated the public docs to use app wording instead of add-on wording where user-facing.
- Synced the app, integration, docs, and release metadata to v0.2.20.

## 0.2.19

- Updated the mount-point checklist wording and default dropdown behavior.
- Synced the app, integration, docs, and release metadata to v0.2.19.

## 0.2.18

- Added the mount-point include/exclude controls with the requested defaults and closed-by-default panels.
- Synced the add-on, integration, docs, and release metadata to v0.2.18.

## 0.2.17

- Added configurable include/exclude controls for the standard Home Assistant mount points.
- Synced the add-on, integration, docs, and release metadata to v0.2.17.

## 0.2.16

- Clarified in the docs and add-on description that this is a config sync tool, not a backup tool.
- Synced the add-on, integration, docs, and release metadata to v0.2.16.

## 0.2.15

- Added explicit AppDaemon sync coverage for `/config/appdaemon/` config and apps.
- Synced the add-on, integration, docs, and release metadata to v0.2.15.

## 0.2.14

- Moved the support section directly under the title and badges in both READMEs.
- Synced the add-on, integration, docs, and release metadata to v0.2.14.

## 0.2.13

- Added live status polling so progress figures repaint during uploads.
- Synced the add-on, integration, docs, and release metadata to v0.2.13.

## 0.2.12

- Added live progress updates to scheduled syncs and clean uploads.
- Synced the add-on, integration, docs, and release metadata to v0.2.12.

## 0.2.11

- Forced live uploads for both sync buttons so dry-run no longer blocks writes.
- Synced the add-on, integration, docs, and release metadata to v0.2.11.

## 0.2.10

- Fixed the manual sync route placement so the add-on boots cleanly again.
- Synced the add-on, integration, docs, and release metadata to v0.2.10.

## 0.2.9

- Added manual sync retention pruning for version snapshots older than seven days.
- Synced the add-on, integration, docs, and release metadata to v0.2.9.

## 0.2.8

- Added visible live upload progress cards for remaining upload/delete counts.
- Made the recommended .gitignore and runtime status sections collapsible.

## 0.2.7

- Updated validation metadata so HACS and hassfest both pass cleanly.

## 0.2.6

- Added explicit button busy states so pressed actions are visible in the UI.

## 0.2.5

- Refreshed the add-on UI with a more polished panel layout and better status hierarchy.

## 0.2.4

- Added live sync progress with current file, remaining counts, and path queues.

## 0.2.3

- Added a recommended .gitignore checklist backed by the local config folder.
- Added cancel-current-upload control for long-running syncs.

## 0.2.2

- Updated the token badge to flip immediately on startup and after device login.

## 0.2.1

- Bumped the add-on/integration version for the next release.

## 0.1.6

- Fixed ingress API path handling in the web UI to avoid 404 responses behind Home Assistant ingress.
- Updated all frontend API calls to use the active ingress base path.

## 0.1.5

- Fixed web UI JSON parsing to handle non-JSON API responses without breaking page load.
- Improved device-flow status handling when auth endpoints are unavailable during upgrade transitions.

## 0.1.4

- Added GitHub OAuth Device Flow to the add-on web UI (start + complete login).
- Added API endpoints for device-flow state/start/complete.
- Updated runtime and docs for the new browser-based authentication path.

## 0.1.3

- Fixed add-on build to install Flask via Alpine packages (`py3-flask`) to avoid PEP 668 pip failures.
- Updated add-on base image handling for Home Assistant Supervisor compatibility.

## 0.1.2

- Added ingress web UI and API endpoints (`/api/health`, `/api/options`, `/api/status`, `/api/sync`).
- Added sync core modules and hash-based changed-file detection.

## 0.1.1

- Stabilized add-on packaging and runtime wiring.

## 0.1.0

- Initial add-on scaffold and repository metadata.
