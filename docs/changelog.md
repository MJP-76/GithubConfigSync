# Changelog

The full 71-release history lives in
[CHANGELOG.md](https://github.com/MJP-76/GithubConfigSync/blob/main/CHANGELOG.md)
(and on
[GitHub Releases](https://github.com/MJP-76/GithubConfigSync/releases)).
The last 5 releases are kept at the top, per the project's changelog rules.

## 1.6.10

- **Chore**: The "Installed / Latest / Latest stable / Available" detail line is
  removed from the add-on updates section. The panel now shows just the status
  badge and the "Show pre-release build updates" toggle — pre-release builds
  are installed from Home Assistant &rarr; Add-ons, and the toggle is what makes
  them appear there as update candidates

## 1.6.9

- **Reliability**: New rate-limit watchdog. GitHub `429` and secondary/abuse
  limits are retried until they clear — or the sync is cancelled — instead of
  failing after 5 attempts. The wait honours `Retry-After` /
  `X-RateLimit-Reset`, a shared gate makes every concurrent upload/delete
  worker hold together so the batch doesn't stampede the API, and a wait can be
  cancelled at any time. The UI shows "waiting" progress instead of freezing
  mid-sync
- **Reliability**: The core rate-limit budget is watched too: when nearly
  exhausted the engine pauses before sending instead of burning requests on
  guaranteed `403`s
- **Fix**: The "Show pre-release build updates" and sync-mode controls were
  missing from the form's auto-save listener list, so changing either on its
  own never persisted — the toggle snapped back on the next load. Both now
  auto-save like every other option
- **Test**: 429/Retry-After backoff, retries past the old 5-attempt cap until
  success, cancel-during-wait aborts, and cancelled rate-limit waits surface as
  a cancelled sync rather than a failure

## 1.6.8

- **Feature**: The update check now reports how many new versions exist and
  names every candidate — pre-releases included when `include_pre_releases` is
  enabled — instead of only the newest. The UI badge reads "Update available
  (N)" and the details line lists each build newer than the installed version
- **Safety**: "Clean Repo" no longer wipes the remote repository. It is now a
  diff-clean: only files present on GitHub but missing from the local config
  are deleted, with per-file progress and cancel support, so it is safe to
  run at any time
- **Feature**: New "Reset Repo" action (`/api/sync/nuke-repo`) replaces the
  whole repository — an empty tree on an orphan commit drops the entire
  history, and every release and tag is deleted. It runs in a handful of
  git-data API calls rather than per-file deletes, restores the starter
  skeleton, and requires typing `RESET <repository>` to confirm
- **Safety**: The sync engine refuses to delete remote files when the local
  scan found no files at all, so a broken scan can never empty the remote repo
- **Reliability**: GitHub rate-limit backoff is capped at 60 seconds per retry
  instead of 300, so a stalled cleanup no longer hangs for minutes
- **Test**: diff-clean and nuke-repo engine paths, history-reset orphan
  commits, release/tag cleanup, the empty-scan guard, the rate-limit cap, and
  the clean-repo/nuke-repo API endpoints

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

_(older releases)_