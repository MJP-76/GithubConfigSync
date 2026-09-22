# Changelog

## Latest Releases

## 1.6.8

- **Feature**: The update check now shows how many new versions exist and names every build (pre-release included when `include_pre_releases` is enabled) newer than the installed version. The badge reads "Update available (N)" and the details line lists each candidate instead of just the newest
- **Safety**: "Clean Repo" no longer wipes the remote repository. It is now a diff-clean: only files that exist on GitHub but are missing from the local config are deleted, with per-file progress and cancel support, so it is safe to run at any time
- **Feature**: New "Reset Repo" action (`/api/sync/nuke-repo`) replaces the entire repository — an empty tree on an orphan commit drops the whole history, and every release and tag is deleted. It runs in a handful of git-data API calls rather than per-file deletes, restores the starter skeleton, and requires typing `RESET <repository>` to confirm
- **Safety**: The sync engine refuses to delete remote files when the local scan found no files at all, so a broken scan can never empty the remote repo
- **Reliability**: GitHub rate-limit backoff is capped at 60 seconds per retry instead of 300, so a stalled cleanup no longer hangs for minutes
- **Test**: diff-clean and nuke-repo engine paths, history-reset orphan commits, release/tag cleanup, the empty-scan guard, the rate-limit cap, and the clean-repo/nuke-repo API endpoints

## 1.6.7

- **Fix**: Key and certificate material can never be synced. SSL/TLS keys and certs (`.pem`, `.key`, `.crt`, `.cer`, `.der`, `.p12`, `.pfx`, `.p8`, `.pub`, `.asc`), SSH keys (`id_rsa`, `id_ed25519`, …) and `.ssh/` folders are hard-excluded from scanning and upload in every sync mode, layered on top of the existing `.gitignore` filtering
- **Fix**: Removed two bogus entries (`include_ssl`, `include_addon_configs`) from the built-in ignored-directories list — leftover option-key names, no directory is ever named that
- **Test**: key/cert/SSH paths are hard-ignored and never enter the hash index; no option-key leftovers in the ignored-dirs list

## 1.6.6

- **Feature**: The `sync_mode` option now actually controls what is synced. In `whitelist` mode (default) only the explicitly enabled paths are synced (the base HA config plus whichever `include_*` mount points are checked), as before. In `blacklist` mode every mounted path is synced except `.gitignore`-ignored patterns. Previously the option was validated and stored but the sync engine never read it, so switching to `blacklist` changed nothing
- **Test**: Engine root selection for whitelist (toggle-filtered) and blacklist (all mounted roots) modes

## 1.6.5

- **Fix**: The add-on `map` is now valid Supervisor mount types. The Supervisor (2026.09+) logged store warnings for the invalid entries `addon_configs:rw`, `backups:rw` and `www:rw` and for the deprecated `config` type — those folders were never actually mounted. `config` becomes `homeassistant_config` pinned to `/config` (`path`), `addon_configs` becomes `all_addon_configs` (mounted at `/addon_configs`), `backups` becomes the valid `backup` type (mounted at `/backup`), and `www` is dropped (www files are already resolved from the config root)
- **Fix**: `include_backups` now reaches the backups it was meant to sync — the engine scanned `/backups`, but the valid Supervisor `backup` mount lands at `/backup`, so the toggle never synced anything
- **Chore**: Removed the deprecated 32-bit `arch` values (`armhf`, `armv7`, `i386`) — the add-on now builds for `aarch64` and `amd64` only
- **Test**: Add-on `map` entries are regression-checked against the Supervisor volume regex (no deprecated `config` type, no bogus type, `homeassistant_config` pinned to `/config`), `arch` excludes deprecated values, and the engine scans the `/backup` mount

## 1.6.4

- **Fix**: The repository marker (`\.github-config-sync-addon\.json`) is rewritten before every sync without the current file SHA, so on an already-marked repo the nightly sync failed with GitHub 422 `"sha" wasn't supplied` (and an earlier 409 `is at "..." but expected "..."` on a stale file), aborting the entire sync each night. The marker writer now reads the existing SHA and updates the file, and the SHA-conflict classifier now treats a 422 `sha wasn't supplied` response as a conflict so the refresh-and-retry path also catches any other SHA-less update
- **Test**: Marker writes pass the existing SHA (and omit it for a fresh repo); 422 missing-SHA responses are classified and recovered with a refreshed SHA

## 1.6.3

- **Fix**: `auto_sync_days` schema is now a nested optional integer list (`["int?"]`). The earlier `list?` form was rejected by the Supervisor's schema parser, dropping the add-on from the store (so no updates were offered); the interim `list(str)` form silently caused `Failed to sync options to Supervisor: HTTP Error 400` on every save, because a flat `list(...)` schema element is an enum, not a list type
- **Fix**: `sync_mode` schema uses pipe-separated enum values without quotes (`list(whitelist|blacklist)?`); the quoted form made the whole enum a single bogus option and rejected the real `whitelist`/`blacklist` value with an options-sync 400
- **Fix**: When the Supervisor rejects an options push, the sync failure log now includes the Supervisor response body (previously only the generic `HTTP Error 400: Bad Request` was shown)
- **Test**: Add-on `schema` values are regression-checked against the Supervisor's own element regex and must match the option keys the app syncs

## 1.6.2

- **Feature**: New `include_pre_releases` option — when enabled, the add-on reports pre-release builds (not just stable ones) in its update check, so a candidate version is visible before it reaches the stable line
- **Feature**: Added `/api/update-check` endpoint and an "Add-on updates" section in the web UI that compares the installed version against the add-on's GitHub releases (server-cached for 5 minutes; fails soft) and points users to install updates from Home Assistant → Add-ons

## 1.6.1

- **Fix**: Sync no longer fails with "Path escapes allowed sync roots" when the `www` mount point is excluded — `www` files are resolved from the config root instead of the container's `/www` path (regression from the mount-point controls)
- **Fix**: `.gitignore` patterns in the config root are now honored during scanning, so UI-managed defaults (e.g. HACS `www/community/`) are excluded
- **Fix**: Removed the vestigial `sync_interval_minutes` option — scheduled sync still uses day-of-week + time selection
- **Fix**: Options pushed to Supervisor are filtered to the add-on schema, fixing `Failed to sync options to Supervisor: HTTP Error 400`
- **Fix**: Scheduled-sync timer can no longer double-schedule when settings are saved while a poll is in flight
- **Chore**: `include_www` now defaults consistently to off across the schema, UI and engine

## 1.5.22

- **Fix**: "Token missing" badge no longer appears when the token is actually fine — a transient GitHub check failure (`error` state) now shows as an amber "Token check failed" badge instead of the red "Token missing", and `/api/status` degrades it back to "Checking token..." so the status poll can never misreport a lost token
- **Fix**: One slow or timed-out GitHub call no longer poisons the token badge for 5 minutes — transient `error` health results are cached for 30s (stable states keep the 5-minute cache), so the badge self-corrects quickly
- **Fix**: Device Flow completion no longer reports "request timed out" mid-authorization — the UI now waits up to 130s for the exchange (server polls GitHub up to 120s) instead of aborting at 10s while the token was still being saved in the background
- **Fix**: Live token health check now uses a bounded 20s GitHub call with a 30s client timeout, so the real result reaches the UI instead of being aborted client-side at 10s
- **Fix**: Auth section no longer expands/collapses confusingly after login — it collapses once a token is present (rate-limited/check-error included), and only stays open for a genuinely missing or expired token
- **Fix**: `_save_state()` is now serialized with a lock so concurrent status polls / sync-progress writes can no longer race and drop the token-health cache entry

## 1.5.21

- **Fix**: Options now actually persist across add-on restarts — Supervisor sync POSTs `{"options": ...}` to `/addons/self/options` (self-alias, no slug needed) so it works for any `hassio_role`, fixing the previously wrong slug (`github_config_sync_web`) and unwrapped payload shape
- **Fix**: `hassio_api: true` added to `config.yaml` so `SUPERVISOR_TOKEN` is injected into the container — without it the Supervisor sync silently skipped and the token was lost on reboot
- **Fix**: `set_options()` guards against a client echoing the masked `********` token placeholder, so a settings save can never overwrite the real saved token with the mask

## 1.5.20

- **Fix**: `/api/status` no longer performs a live GitHub call — it reads token health only from the state cache, so the 2-second status poll (and page-load render) can never be blocked by a slow or failing GitHub API request
- **Fix**: Added dedicated public `/api/token/health` endpoint for the live GitHub token check
- **Fix**: Frontend calls `/api/token/health` on a 60-second throttle (page load, visibility change, settings save, device-flow completion) instead of every status poll; `fetchJson` now aborts hung requests after 10s

## 1.5.19

- **Fix**: `_via_ingress_proxy()` now checks `X-Hass-Source: core.ingress` + private IP FIRST (primary), Supervisor IP fallback — works regardless of Docker networking changes
- **Fix**: Frontend fetches version from `/api/health` BEFORE Promise.allSettled — version shows instantly, no waiting for GitHub API call in `/api/status`
- **Fix**: `/api/health` now returns `repo_versions` for early fetch
- **Fix**: Removed dead code in `_token_health()`, IPv6 support in `_is_private_ip()`, visibility change loads both status + options

## 1.5.18

- **Fix**: Removed dead code in `_token_health()` (three unreachable return blocks from merge conflict)
- **Fix**: Page-load Promise.allSettled no longer bails on `loadOptions()` auth failure — versions now display before auth
- **Fix**: Visibility change handler now calls both `loadStatus()` and `loadOptions()` to restore full UI state
- **Fix**: IPv6 support in `_is_private_ip()` (ULA fc00::/7, link-local fe80::/10, loopback ::1)
- **Fix**: Supervisor sync token persistence across restarts

## 1.5.17

- **Fix**: `/api/status` is public (no auth) — returns version info so versions display on UI load before authentication

## 1.5.16

- **Fix**: `/api/status` is now public (no auth required) — returns version info, repo versions, and token_health so versions display before user authenticates

## 1.5.15

- **Fix**: Removed duplicate `_persist_options` function definition (second definition was overwriting the first)
- **Fix**: Token now persists across restarts via both Supervisor config store and webui_options.json

## 1.5.14

- **Fix**: Re-added Supervisor option sync with graceful error handling — token now synced to Supervisor config store after device flow completion and settings update, surviving add-on restarts
- **Fix**: Graceful Supervisor API error handling (logs warning on 403/other errors, doesn't crash)

## 1.5.13

- **Fix**: Token health check cache key now uses stable SHA256 (not Python's randomized hash()) — cache now persists across restarts, stopping 2s polling from hitting GitHub rate limits after the first successful check

## 1.5.12

- **Fix**: Token health check cache key uses hash(token) to avoid issues with short tokens
- **Fix**: Improved rate limit detection in token health check — checks for multiple keywords (rate limit, secondary rate limit, abuse detection, x-ratelimit-remaining, x-ratelimit-reset) in error body
- **Fix**: Added warning log for failed token health checks to aid debugging

## 1.5.11

- **Fix**: Token health check now caches results (5 min valid / 30s errors), distinguishes rate limits from auth failures, and returns a `rate_limited` state instead of collapsing into `expired`
- **Fix**: Frontend handles `rate_limited` state — shows "Rate limited" badge, doesn't auto-collapse auth section, pauses polling when tab/iframe hidden (visibilitychange), resumes on visibility restore

## 1.5.10

- **Fix**: Removed failing Supervisor API sync call (403 Forbidden) — token persists via webui_options.json which _merge_options() already reads

## 1.5.9

- **Debug**: Added detailed logging for Supervisor option sync and ingress auth checks to diagnose token persistence issues

## 1.5.8

- **Fix**: Token from device flow now synced to Supervisor — persists across add-on restarts and UI navigation

## 1.5.7

- **Fix**: Device flow endpoints (`/api/auth/device*`) no longer require authentication — they bootstrap the GitHub token (regression in 1.5.6 where device login was broken)
- **Fix**: `sync_mode` validation in payload (must be `whitelist` or `blacklist`)
- **Fix**: Device flow token exchange caps `slow_down` retries at 10 (previously unbounded)

## 1.5.6

- **Security fix**: API authentication now works. Requests are trusted as ingress-authenticated only when they originate from the Supervisor proxy (peer-address check) — the legacy IngressSession header check, which no Home Assistant version sets, was removed
- All GET API endpoints now require authentication (via ingress or Bearer github_token); previously only POST endpoints were guarded
- Fixed sync_versions.py: now updates hacs.json and PROJECT.md, and no longer rewrites a stale APP_VERSION constant in server.py (version is auto-read from config.yaml)

## 1.5.5

- **Security fix**: Sensitive file scanning now actually blocks uploads (was previously report-only after sync)
- Added is_sensitive_candidate() name-pattern check to is_ignored() in build_hash_index
- Added content scanning (_is_file_sensitive) to build_hash_index to detect embedded secrets in file contents
- Removed dead code: _require_ingress decorator and SyncEngine._delete_remote_tree_except
- Added _require_auth guard on all POST endpoints (ingress token or configured github_token Bearer)
- Path safety checks now use is_relative_to instead of string prefix matching
- Retry with exponential backoff on transient GitHub 5xx errors (500/502/503/504)
- Pinned base image to ghcr.io/home-assistant/base:3.24-2026.06.1 (reproducible builds)
- Legacy custom_components stripped to redirect-only (no parallel sync implementation)

## 1.5.4

- GitHub token now syncs from the HA config flow to the add-on via the Supervisor API (webui_options.json) instead of a direct filesystem write

## 1.5.3

- Added SHA conflict retry with exponential backoff (up to 3 attempts) for GitHub API push operations
- Token sync: HA config flow now writes github_token to webui_options.json so add-on reads it
- Version auto-read from config.yaml via regex — single source of truth
- Added core.config_entries and .env to built-in ignore patterns
- Fixed CI badge to point to validate.yml for repos without ci.yml

## 1.5.2

- Security hardening: all include_* options (include_ssl, include_addon_configs, include_media, include_share, include_backups, include_www) now default to false
- Added include_ssl and include_addon_configs to IGNORE_DIRS
- Moved sync mode into its own section in web UI between scheduled sync and mount points
- Added Reset to Defaults button for .gitignore patterns

## 1.5.1

- All settings moved to web UI (config page only has github_repository/branch/token)
- Removed sync_interval, folder selection, dry_run, version_retention, and sync_mode from config.yaml options
- Kept optional schema entries for backward compatibility
- Dry run mode now default ON
- Web UI checkboxes all default unchecked

## 1.5.0

- Feature: whitelist/blacklist sync mode selection
- Feature: optional include_* directory flags for fine-grained sync control
- Restructured config.yaml: only github_repository/branch/token in options
- Added _repo_sync_config and _sync_config updates for new fields
- Updated all SyncConfig creation sites with new defaults

## 1.4.2

- Security fix: removed token from URL query params, use Authorization header only
- Fixed add-on marker file path for non-root config dirs
- Updated web UI to use Bearer token auth header
- Added safety check: refuse to sync if token is empty

## 1.4.1

- Moved Scheduled sync, Mount points, .gitignore, and Dry run into Installation and Usage card as numbered sub-sections 4–7
- Removed standalone Sync options card
- Dry run mode now includes explanatory description text

## 1.4.0

- Restructured UI: Installation card now contains Device Login, Repository Setup, Target Repository, and action buttons
- Sections auto-expand when not configured, stay collapsed when configured
- Renamed "Installation" to "Installation and Usage"
- Moved "Keep versions on GitHub" into Scheduled sync section
- Removed "Auto-sync pushes changes" toggle — scheduled sync always pushes when enabled
- Removed Troubleshooting options section
- Added Skipped (unchanged) count to sync activity display
- SHA conflict retries with backoff (up to 3 attempts)
- Version auto-read from config.yaml — single source of truth
- Reworded skeleton README

## 1.3.3

- Merged safety notes into single block at top of config card
- Moved .gitignore entries under Mount points section
- Moved runtime status into Diagnostics section with download button
- Renamed Danger Zone to collapsible red section, removed duplicate security text
- Added Safety & Security Recommendations section

## 1.3.2

- Moved "Keep versions on GitHub" into the Scheduled sync section
- Removed "Auto-sync pushes changes (ignores dry run)" — scheduled sync always pushes when enabled

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
