# Changelog

The full 71-release history lives in
[CHANGELOG.md](https://github.com/MJP-76/GithubConfigSync/blob/main/CHANGELOG.md)
(and on
[GitHub Releases](https://github.com/MJP-76/GithubConfigSync/releases)).
The last 5 releases are kept at the top, per the project's changelog rules.

## 1.6.4

- **Fix**: The repository marker is rewritten before every sync without the
  current file SHA, so on an already-marked repo the nightly sync failed with
  GitHub 422 `"sha" wasn't supplied` (and earlier, a 409 stale-SHA conflict),
  aborting the entire sync. The marker writer now reads the existing SHA and
  updates the file, and 422 missing-SHA responses are treated as SHA conflicts
  for the refresh-and-retry path
- **Test**: Marker SHA passthrough, fresh-repo omit, and 422 missing-SHA
  recovery

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

_(older releases)_