# Changelog

The full 71-release history lives in
[CHANGELOG.md](https://github.com/MJP-76/GithubConfigSync/blob/main/CHANGELOG.md)
(and on
[GitHub Releases](https://github.com/MJP-76/GithubConfigSync/releases)).
The last 5 releases are kept at the top, per the project's changelog rules.

## 1.6.7

- **Fix**: Key and certificate material can never be synced. SSL/TLS keys and
  certs (`.pem`, `.key`, `.crt`, `.cer`, `.der`, `.p12`, `.pfx`, `.p8`, `.pub`,
  `.asc`), SSH keys (`id_rsa`, `id_ed25519`, …) and `.ssh/` folders are
  hard-excluded from scanning and upload in every sync mode
- **Fix**: Removed two bogus entries (`include_ssl`, `include_addon_configs`)
  from the built-in ignored-directories list
- **Test**: key/cert/SSH hard-ignore coverage and hash-index exclusion

## 1.6.6

- **Feature**: The `sync_mode` option now actually controls what is synced. In
  `whitelist` mode (default) only the explicitly enabled paths are synced (the
  base HA config plus whichever `include_*` mount points are checked). In
  `blacklist` mode every mounted path is synced except `.gitignore`-ignored
  patterns. Previously the option was validated and stored but the sync engine
  never read it, so switching to `blacklist` changed nothing
- **Test**: Engine root selection for whitelist (toggle-filtered) and blacklist
  (all mounted roots) modes

## 1.6.5

- **Fix**: Add-on `map` entries are now valid Supervisor mount types. The
  Supervisor logged store warnings for the invalid `addon_configs:rw`,
  `backups:rw` and `www:rw` entries and for the deprecated `config` type, so
  those folders were never actually mounted. `config` becomes
  `homeassistant_config` pinned to `/config`, `addon_configs` becomes
  `all_addon_configs` (mounted at `/addon_configs`), `backups` becomes the
  valid `backup` type (mounted at `/backup`), and `www` is dropped (www files
  are already resolved from the config root)
- **Fix**: `include_backups` now scans `/backup` instead of the never-mounted
  `/backups`
- **Chore**: Removed deprecated 32-bit `arch` values (`armhf`, `armv7`,
  `i386`); the add-on builds for `aarch64` and `amd64`
- **Test**: `map` and `arch` regression checks plus the backup-root scan test

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

_(older releases)_