# Changelog

## Latest Releases

## 1.3.1

- Removed snapshot/versioning system — replaced by GitHub releases
- Removed sync_interval_minutes and manual_version_retention_days options
- Renamed "Run Sync Now" to "Sync Now"

## 1.3.0

- Feature: scheduled sync with day-of-week and time-of-day selection
- Feature: optional dated release creation before each scheduled sync (tagged dd/mm/yy hh:mm:ss)
- Feature: auto-prune old sync releases based on "Keep versions on GitHub" count
- Feature: new GitHub API methods for release management (create, list, delete)
- Scheduler polls every 30 seconds and matches against configured days and time
- Scheduler uses local time of the Home Assistant server

## 1.2.0

- Feature: auto-sync scheduler — runs sync on a configurable interval in the background
- Scheduler re-reads settings each cycle, so interval/token/branch changes take effect immediately
- "Auto-sync pushes changes (ignores dry run)" checkbox now controls whether the scheduler does live pushes or dry-runs
- Scheduler status shown in version badge (next run time and mode)
- Renamed UI labels for clarity

## 1.1.3

- Fix: removed ingress header validation — breaks when HA is behind a reverse proxy that strips headers. HA ingress URL token alone is sufficient authentication.

## 1.1.2

- Fix: removed ingress requirement from device auth endpoints. Device flow was blocked by the security hardening in 1.1.1, preventing GitHub login from completing.

## 1.1.1

- Security hardening: ingress header validation on mutating API endpoints.
- Security hardening: path ancestry checks on filesystem operations.
- Security hardening: diagnostics log redaction strips tokens, secrets, and URLs.
- Consolidated project documentation into single PROJECT.md.
- Rewrote README for user-facing clarity.
- Added experimental status badge and My Home Assistant install button.

## 1.0.50

- Always verify managed repo status against the live GitHub marker file, never trust the cache.
- Removed stale cache entries from keeping unmanaged repos in the list.

## 1.0.49

- Fixed cache default: `managed` now defaults to `False` instead of `True`.
- Repos without a marker file no longer show as managed.

## 1.0.48

- Removed `_repo_safety_state` and `_existing_repo_confirmation_error` checks from the clean-repo endpoint.
- Clean-repo now only requires the confirmation dialog.

## 1.0.47

- Removed addon marker file (`.github-config-sync-addon.json`) from source repos.
- Cleaned `.gitignore` (removed stale HA config entries).
- Added cancel checks to clean-repo.
- Added atomic-operation warning to Clean Upload/Repo confirmation dialogs.
- UI loads live repos on init instead of stale cache.
- Fixed `_repo_safety_state()` missing return values.

## 1.0.46

- Added atomic-operation warning to Clean Upload and Clean Repo confirmation dialogs.
- Both now warn that the operation cannot be cancelled once started.

---

## Older Releases

## 1.0.40

- Added `hacs_frontend` and `node_modules` to the built-in ignore directories so compiled frontend bundles are no longer synced.
- Added `*.js.map` to the built-in ignore patterns to skip JavaScript source maps.
- Added automatic retry with backoff when the GitHub API returns a rate-limit error (HTTP 403).
- Rate-limit retries parse the `X-RateLimit-Reset` header to wait exactly until the window resets, with exponential backoff as fallback.

## 1.0.35

- Stable release 1.0.35 promoting the current dev repository-management flow.
- Stable keeps the adopted-repos-first picker, explicit repository adoption, and opt-in expansion to other accessible repos.
- Stable also keeps the newer upload-progress cleanup so finished or failed runs do not stay pinned on a stale file name.

## 1.0.34

- Stable release 1.0.34 for the stuck upload progress fix.
- Cleared stale sync progress when a run completes, fails, or starts a fresh run.
- Upload and delete progress now switches from the last submitted filename to a waiting state while parallel GitHub calls finish.
- Version snapshot uploads now report their own phase instead of leaving the UI pinned on the last config file name.

## 1.0.33

- Stable release 1.0.33 for the repository adoption flow.
- Load Repositories now shows adopted or marker-managed repos by default.
- Ticking the existing-repo checkbox expands the picker to show other accessible repos for adoption.
- Existing unmanaged repos must be explicitly adopted before write actions can target them.
- Clean Upload and Clean Repo both restore the starter skeleton and refresh the add-on marker.

## 1.0.32

- Add compatibility support for the managed repo picker endpoint.

## 1.0.26

- Renamed the defaults button and made it preserve user-selected ignore entries.

## 1.0.25

- Added a Select All toggle to the grouped ignore suggestions UI.

## 1.0.24

- Default-selected ignore recommendations now start checked when no local `.gitignore` exists.

## 1.0.23

- Added a Select All checkbox for the ignore recommendations list.

## 1.0.22

- Grouped the ignore suggestions into labeled sections for easier scanning.

## 1.0.21

- Added a one-click button to write the built-in `.gitignore` defaults.

## 1.0.20

- Added `.ruff.toml` to the built-in ignore defaults.

## 1.0.19

- Made repository selection auto-save with the rest of the settings and removed the separate Save Settings button.

## 1.0.18

- Clean Repo now emits live delete counts in the activity panel while it wipes the remote tree.

## 1.0.17

- Startup now falls back to a supported-repo refresh if the cache is empty.

## 1.0.16

- Removed the all-repos button and fixed the supported-repo picker refresh path.

## 1.0.15

- Startup now loads cached supported repos, and the manual button refreshes the supported repo list.

## 1.0.14

- Added a startup repo list plus an on-demand add-on repo filter to avoid probing on load.

## 1.0.13

- Published a fresh dev release for the repo picker fix.

## 1.0.12

- Restored a safe repo picker filter that only shows add-on-style repositories without probing repo contents.

## 1.0.11

- Bumped the dev lane again so Home Assistant gets a fresh add-on index entry.

## 1.0.10

- Synced the embedded app version with the published add-on version so HA stops showing the old build number.

## 1.0.9

- Moved the live activity status into a single panel for both upload and delete work.
- Added clean repo status details to the same activity panel.

## 1.0.8

- Cleared stale startup sync state on app boot.
- Removed the repo list contents probe so the picker no longer burns GitHub rate limit on load.

## 1.0.7

- Fixed the stale running upload state so rebuilds clear canceled runs.
- Added a retry for DELETE content requests when GitHub returns a stale SHA conflict.

## 1.0.6

- Fixed startup flicker by only showing Ready after startup loads finish successfully.
- Fixed repo picker rate-limit errors so they no longer crash the page.
- Made the repo picker header stay on one line with the load button beside it.

## 1.0.5

- Added default ignore rules for common Home Assistant runtime, editor, and secret files.
- Added sensitive-file scanning so suspicious files are skipped and reported in a root warning file.
- Kept the repo picker and load button on one line in the UI.

## 1.0.4

- Added repo marker support so clean actions can verify add-on-managed repositories.
- Filtered unsafe repositories out of the repo picker.
- Made Clean Repo do a full remote reset, then restore the skeleton and refresh the marker.
- Made Clean Upload refresh the repo marker after the live upload finishes.

## 1.0.3

- Removed the Latest changes panel from the app UI.
- Fixed stale state so a new sync clears the previous result and scan.

## 1.0.2

- Fixed upload progress so the remaining counters count down during the run.
- Kept the repo picker and load button on one line.

## 1.0.1

- Fixed the startup crash caused by the new sensitive upload warning path.

## 1.0.0

- Promoted the main repo to the first stable release.
