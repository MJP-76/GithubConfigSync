# Changelog

## Unreleased

- Preparing the v0.2.6 release bump.

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
