# Changelog

The full 71-release history lives in
[CHANGELOG.md](https://github.com/MJP-76/GithubConfigSync/blob/main/CHANGELOG.md)
(and on
[GitHub Releases](https://github.com/MJP-76/GithubConfigSync/releases)).
The last 5 releases are kept at the top, per the project's changelog rules.

## 1.7.7

- **New: one-shot "Migrate from flat layout to structured" tick box.** Tick it and the next sync clears the repository root of everything that now lives under `config/`, in that sync's single commit, keeping this add-on's own marker, `README.md` and `repository.yaml`. It then writes `.github-config-sync-migrated.json` to the repository root and greys itself out permanently. Requires Layout to be `prefixed`.

- **The Layout dropdown has never worked.** `repo_layout` was missing from the options the UI posts and options are replaced wholesale on save, so the choice was erased immediately and the layout reverted to the `prefixed` default. A payload without the key now keeps what is stored.

- **The migration reads the repository rather than the scan baseline.** A baseline only holds what a previous sync recorded, so after a run that scanned nothing every operation reading it returned an empty plan while appearing to succeed — which is why normal sync, Clean Repo and Migrate Layout were all no-ops.

## 1.7.6

Fixes the Sync button, which was reporting success without syncing anything.

- **Manual sync ignored your selection.** It re-created its config from a field list copied from a much older version and dropped `sync_paths`, `safe_config_paths`, `security_override_all_filters` and `repo_layout`. Whitelist with an empty selection scans nothing, so every manual sync returned "Sync completed" for a run that touched no files - while the scheduled sync, which does not rebuild, kept working.

- **Clean Upload had the same bug and is worse for it:** it forces `dry_run` off while dropping `repo_layout`, so a flat repository would have staged files under `config/` beside the originals.

- Both rebuilds are gone, pinned by a structural test, an endpoint test, and a regression test that posts to the endpoint the Sync button actually calls.

**Upgrading from 1.7.1 or earlier:** set **Layout** to `Flat` (or run **Migrate Layout**) before your next sync - `repo_layout` now defaults to `prefixed`.

## 1.7.5

Fixes the cause of a sync that hangs while reporting itself as running.

- **One client's rate limit could stall every other client.** The backoff state was module-global, so any request that drew a rate limit made *every* GitHub client in the process wait on it, including clients that had hit no limit of their own and could not clear it.

- **In practice the add-on was stalling itself.** Its update check runs unauthenticated, because it reads the add-on's public repository and cannot use your token, and unauthenticated requests share GitHub's much smaller 60/hour per-IP budget. When that was spent, the update check opened a backoff of roughly half an hour and authenticated syncs queued behind it, reporting "running" while waiting on a limit they had not hit.

- The backoff state now belongs to each client, and the update check gives up on a rate limit rather than sleeping through one. Syncs that hit a real limit still back off and retry exactly as before.

## 1.7.4

Fixes 1.7.3's own logging, which never reached the log.

- **The sync lifecycle lines added in 1.7.3 were discarded.** The app configured no logging at all, so Python's fallback handler dropped everything below WARNING - including the new start and finish lines. A sync that ran cleanly was indistinguishable in the log from one that never started, which is the exact ambiguity 1.7.3 was meant to remove.

## 1.7.3

Fixes a sync that reports itself as running and then does nothing.

- **The rate-limit gate outlived the sync that opened it.** It was module-global and cleared only as time passed over; a cancelled or failed sync left it open, and the next run - a manual one especially - sat waiting on it, reporting "running" while making no requests at all. Only a restart cleared it. Every sync now clears the gate when it ends, however it ends.
- **A rate limit that does not clear fails instead of retrying forever.** The request loop had no ceiling, so a permanently refused request retried for hours with no error and no explanation. It now honours the wait GitHub asks for, three times, then raises.
- **GitHub's explanation is logged and kept in the error**, so an exhausted quota can be told apart from a token that cannot reach the repository.
- **Waiters are no longer released in lockstep.** They fired simultaneously, which draws a secondary rate limit that re-arms the gate, so the backoff could never converge.
- **Syncs are logged.** There were no log calls in the sync engine or server at all, so a sync starting, running, succeeding or failing produced no output. Start, outcome, counts and duration are now recorded.

## 1.7.2

Prefixed repository layout, a size cap, and selection by picking only.

- **The config directory now syncs to `config/` inside the repository**, so it no longer shares a namespace with the add-on's own files. Mounts keep their existing names. Prefixed is the default; `flat` remains available. Upgrading does not move anything - **Migrate Layout** in the Danger Zone does, after a dry run showing exactly what will move.
- **Files over 50 MB are skipped and listed by name** instead of failing the entire run with a 422, and are protected from Clean Repo deletion.
- **The free-text path box is removed.** Every file is reachable from the tree, which cannot be mistyped; `safe_config_paths` remains for globs.
- **A sync is now one commit instead of one per file.** Per-file commits cost three API calls a file, so a 224-file repository needed over 600 calls - enough to trip the rate limiter and, if a run failed partway, leave the repository in a state matching no plan the user had seen. Staging blobs and writing one tree, commit and ref update makes it N+3 and the run atomic. Deletes are staged in the same commit, a concurrent push is no longer overwritten, and the executable bit is preserved.

## 1.7.1

Fixes three bugs reported in [#44](https://github.com/MJP-76/GithubConfigSync/issues/44). This replaces 1.7.0, which is withdrawn.

- **Fix: changing the selection no longer deletes files from the repository.** Deletion was computed as "in the previous scan but not this one", which cannot tell a file removed from disk from a file the current selection no longer covers. Narrowing a selection therefore reclassified everything outside it as deleted and removed it. Out of scope now means leave alone: a previously synced path is removed only when it is genuinely absent from disk. **Clean Repo is unchanged** - it is an explicitly destructive action and keeps removing everything the scan does not cover.
- **Fix: dry run no longer writes the scan baseline.** The preview was persisting the very index the next sync diffs against, so the two stopped agreeing about what would change.
- **Fix: `/config` now selects the config root.** It normalised to the literal folder `config` and matched none of the keys it was meant to cover, so it silently synced nothing.

## 1.7.0

First stable release of the sync selection rework, consolidating the 1.6.16-1.6.21 pre-releases.

### Sync Selection

Mount points, recommended `.gitignore` entries and dry run are now one section, and its options follow the mode.

| Mode | What you pick | Security checks |
|---|---|---|
| **Whitelist** | files and folders you select - nothing selected syncs nothing | on |
| **Blacklist** | the default folders | on |
| **Override** | files and folders you select | **off** |

- **The sync picker replaces the drill-down browser.** Folders expand and collapse in place, mount points are browsable, and every row can be selected wholesale or individually. A path or glob can also be typed directly.
- **The mount tick boxes are gone.** The picker is now the single selector; `include_*` is derived from the selection on save.
- **Breaking:** the built-in `esphome/*.yaml` / `zigbee2mqtt/*.yaml` allowlist is removed. It bypassed the security checks in every mode, which contradicted what the modes are for. To sync credential-bearing config, select it under **Override**.
- The Danger Zone's security override moved to the mode dropdown; the card now points there and keeps its destructive operations.

### Security

- **The runtime floor is absolute.** Databases, WAL/SHM, logs, lockfiles, caches, `.storage`, `.git` and `node_modules` are excluded in every mode - no mode can re-enable them, because this add-on syncs configuration rather than backing it up.
- **`.gitignore` always wins**, in every mode.
- `.ssh` was reclassified from runtime to credential, so Override reaches it consistently with `id_rsa`.
- The sensitive-file report covers only paths you selected, so it describes what was blocked rather than everything on disk that looks sensitive.

### Fixes

- Selecting a whole mount in the tree did nothing - `_mount_has_selection` matched only the slash form, so the exact name never counted and the root was never walked.
- Picking paths never saved them: there is no Save button, so the 900ms debounce meant a reload inside that window discarded the pick.
- Rapid selection changes were lost on reload, because a reload cancels any fetch still in flight. Options now flush with `sendBeacon` on `pagehide`/`beforeunload`.
- An unselected `/config` was hashed and then discarded; a mount-only selection used to SHA-256 the whole config tree.
- `/config/www` was walked twice - once as part of `/config`, once as its own root.
- `/api/sync/tree` was bound to a helper rather than the endpoint view, so the picker could not load at all.

### Migration

Existing installs are seeded with the config root so their sync does not silently go quiet, saved mount ticks become explicit selections, and the Danger Zone checkbox becomes Override mode.

## 1.6.15

- **Fix**: Safe config paths were still dropped by the content-based secret scan. ESPHome and Zigbee2MQTT configs embed `password:`/`api_key:` inline, so allowlisted files were excluded despite matching the allowlist. Allowlisted paths now bypass both name and content checks and are no longer reported as sensitive.
- **Fix**: The "Override all security filters" option did not actually bypass hard excludes. The `override` flag was accepted but never applied, so `secrets.yaml`, `*.pem` and similar stayed blocked even with the option enabled. The security override now works as documented.
- **Feature**: Safe config paths are now user-editable via **Settings -> 6. Safe config paths** (new `safe_config_paths` option, one glob per line, case-insensitive, `*` matches across directories). Built-in entries are always active.
- **Hardening**: Runtime artifacts (databases, WAL/SHM, logs, lockfiles, caches, `.storage`, `.git`, `node_modules`) are now a distinct tier that neither the allowlist nor the security override can re-enable.
- **Docs**: Documented the `/config/.gitignore` location and how it interacts with the allowlist.

## 1.6.14

- **Feature**: Add targeted allowlist for safe config paths (esphome/*.yaml, esphome/**/*.yaml, zigbee2mqtt/configuration.yaml, zigbee2mqtt/*.yaml) so ESPHome/Zigbee2MQTT configs bypass sensitive-file heuristics without requiring a global override. Runtime artifacts (DBs/WAL/SHM, logs, locks, caches) remain excluded.

## 1.6.13

- **Feature**: Added a Danger Zone option to override all security filters (hard-excludes, name/content secret detection). When enabled, the sync bypasses security filters; audit trail and private-repo gating groundwork in place. This is strictly opt-in and carries the risks stated in the documentation disclaimer.

## 1.6.12

- **Docs**: Added a Safety & Liability Disclaimer to clarify this is a config sync tool (not a backup), users assume all risks, and the maintainer accepts no responsibility for data loss/credential exposure from using advanced features.

## 1.6.11

- **Chore**: The Stable/Dev version pills are removed from the add-on header and
  the stale `repo_versions` payload is dropped from `/api/health` and
  `/api/status` — both only ever echoed the installed version. The add-on update
  badge is now the single place the version shows: "Up to date: v1.6.x" or
  "Update available: v1.6.10", with the candidate tag included for pre-releases
  when the toggle is on

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

_(older releases)_