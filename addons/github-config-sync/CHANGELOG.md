# Changelog

## Unreleased

- Add debounced autosave in the web UI so settings persist without manual Save clicks.

## 0.2.60

- Add debounced autosave in the web UI so settings persist without manual Save clicks.

- Clean Upload now always runs live too, matching Clean Repo.

## 0.2.59

- Clean Upload now always runs live too, matching Clean Repo.

- Quiet Flask/Werkzeug access logs so repeated status polling does not flood the add-on log.

## 0.2.58

- Quiet Flask/Werkzeug access logs so repeated status polling does not flood the add-on log.

- Bundle the starter README and repository.yaml inside the add-on image so Clean Repo can restore them.

## 0.2.57

- Bundle the starter README and repository.yaml inside the add-on image so Clean Repo can restore them.

- Force a fresh add-on release to pick up the cleaned repo restore path in Home Assistant.

## 0.2.56

- Force a fresh add-on release to pick up the cleaned repo restore path in Home Assistant.

- Main repo is now stable-only; numeric sequential release wording now replaces the old stable/dev phrasing.

## 0.2.55

- Force a fresh dev image pull for the Clean Repo skeleton restore path.

## 0.2.54

- Fixed Clean Repo so it always performs the live wipe-and-restore flow.

## 0.2.53

- Clean Repo now ignores dry run and always performs the wipe+restore flow.
- Recombined Clean Repo and skeleton restore into one flow.

## 0.2.52

- Added a scheduled-sync override checkbox so automated runs can ignore dry run while manual actions stay preview-only.
- Clean Repo now performs a true wipe and restores the starter skeleton in one process.

## 0.2.51-dev

- Replaced the custom confirmation modal with native browser confirms to avoid add-on UI runtime errors.

## 0.2.50-dev

- Confirmed the add-on UI modal close handling is inline and scope-safe.

## 0.2.49-dev

- Confirm modal close handling is now inlined to avoid scope-related JS errors.

## 0.2.48-dev

- Fixed the remaining modal close handler scope issue in the add-on UI.

## 0.2.47-dev

- Removed remaining modern JavaScript syntax from the add-on UI so older Home Assistant webviews can initialize it.

## 0.2.46-dev

- Switched the add-on UI to older-browser-compatible JavaScript so the page can initialize correctly in Home Assistant.

## 0.2.45-dev

- Fixed the add-on UI initialization bug caused by the confirmation modal helper nesting.

## 0.2.44-dev

- Added confirmation prompts for Clean Upload and Clean Repo Skeleton, and removed the in-UI release suggestion notice.

## 0.2.43-dev

- Added a separate Cancel Process button in the danger zone for stopping the current job.
## 0.2.39

- Stable release baseline for the main repository.

## 0.2.40-dev

- Moved the danger-zone warning into the repo setup section and made the danger wording consistently bold red.
- Added app/header release metadata improvements for dev testing.

## 0.2.36

- Added the `x`/`y`/`z` release-track selector wording to the UI and backend settings.
- Continued the security-focused UI and docs updates.

## 0.2.35

- Added the remote-delete/local-file caution to the docs and app page.
- Clarified that clean upload deletes only remote GitHub content.
- Added danger-zone security updates: private repos only, sensitive-path filtering, and two-way sync warnings.

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
