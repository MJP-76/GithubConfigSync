# Changelog

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
