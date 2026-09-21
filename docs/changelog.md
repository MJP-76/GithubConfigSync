# Changelog

The full 71-release history lives in
[CHANGELOG.md](https://github.com/MJP-76/GithubConfigSync/blob/main/CHANGELOG.md)
(and on
[GitHub Releases](https://github.com/MJP-76/GithubConfigSync/releases)).
The last 5 releases are kept at the top, per the project's changelog rules.

## 1.6.3

- **Fix**: `auto_sync_days` schema is now a nested optional integer list
  (`["int?"]`). The earlier `list?` form was rejected by the Supervisor's
  schema parser, dropping the add-on from the store (so no updates were
  offered); the interim `list(str)` form silently caused
  `Failed to sync options to Supervisor: HTTP Error 400` on every save,
  because a flat `list(...)` schema element is an enum, not a list type
- **Fix**: `sync_mode` schema uses pipe-separated enum values without quotes
  (`list(whitelist|blacklist)?`); the quoted form made the whole enum a single
  bogus option and rejected real values with an options-sync 400
- **Fix**: Supervisor options-sync failures now log the Supervisor response
  body instead of the generic `HTTP Error 400: Bad Request`
- **Test**: Add-on schema values are regression-checked against the Supervisor
  element regex and must match the option keys the app syncs

## 1.6.2

- **Feature**: New `include_pre_releases` option — when enabled, the add-on
  reports pre-release builds (not just stable ones) in its update check, so a
  candidate version is visible before it reaches the stable line
- **Feature**: Added `/api/update-check` endpoint and an "Add-on updates" section
  in the web UI that compares the installed version against the add-on's GitHub
  releases (server-cached for 5 minutes; fails soft) and points users to install
  updates from Home Assistant → Add-ons

## 1.6.1

- **Fix**: Sync no longer fails with "Path escapes allowed sync roots" when the
  `www` mount point is excluded — `www` files are resolved from the config root
  instead of the container's `/www` path (regression from the mount-point
  controls)
- **Fix**: `.gitignore` patterns in the config root are now honored during
  scanning, so UI-managed defaults (e.g. HACS `www/community/`) are excluded
- **Fix**: Removed the vestigial `sync_interval_minutes` option — scheduled
  sync still uses day-of-week + time selection
- **Fix**: Options pushed to Supervisor are filtered to the add-on schema,
  fixing `Failed to sync options to Supervisor: HTTP Error 400`
- **Fix**: Scheduled-sync timer can no longer double-schedule when settings are
  saved while a poll is in flight
- **Chore**: `include_www` now defaults consistently to off across the schema,
  UI and engine

## 1.6.0

- **Feature**: Reset to Defaults button for ignore patterns in web UI
- **Fix**: Reset to Defaults button was missing its event handler (Uncaught TypeError)
- **Fix**: Add-on rebuild via Supervisor API now works correctly

## 1.5.22

- **Fix**: "Token missing" badge no longer appears when the token is actually
  fine — transient GitHub check failures now show as an amber "Token check
  failed" badge instead of a red "Token missing"
- **Fix**: One slow/timed-out GitHub call no longer poisons the token badge —
  transient `error` health results cache for 30s (stable states keep 5m)
- **Fix**: Device Flow completion no longer reports "request timed out"
  mid-authorization — UI waits up to 130s (server polls GitHub up to 120s)
- **Fix**: Live token health check uses a bounded 20s GitHub call with a 30s
  client timeout
- **Fix**: `_save_state()` is now lock-serialized so concurrent status
  polls/sync writes can no longer drop the token-health cache entry

_(older releases)_