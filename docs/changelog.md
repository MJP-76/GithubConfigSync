# Changelog

The full 71-release history lives in
[CHANGELOG.md](https://github.com/MJP-76/GithubConfigSync/blob/main/CHANGELOG.md)
(and on
[GitHub Releases](https://github.com/MJP-76/GithubConfigSync/releases)).
The last 5 releases are kept at the top, per the project's changelog rules.

## 1.6.20

- **Fix**: Selections were still being lost on reload. Save was debounced by 900ms, and with no Save button to fall back on, picking a folder and reloading before the timer fired discarded it - which is exactly what a picker is normally followed by. Explicit Select/Remove now commits immediately; the debounce stays for typing into fields.

## 1.6.19

- **UI**: The mount tick boxes are gone. The sync picker is now the single place paths are chosen - it already showed every mount as a top-level row, so the checkboxes duplicated it. `include_*` is now derived from the selection on save rather than being a control of its own.
- **Fix**: Selecting a whole mount in the tree did nothing. `_mount_has_selection` only matched the slash form (`media/`), so the exact name `media` never counted and `/media` was never walked. The old tick box was the only thing that worked, which is why the duplication was invisible.
- **Fix**: Picking paths in the tree never saved them. There is no Save button - options only persist through autosave, which was wired to form controls and not to the picker - so selections were lost unless another control happened to be touched afterwards.
- **Performance**: The configuration root is no longer hashed when nothing selected lives inside it. A mount-only selection previously ran a full SHA-256 over `/config` and discarded every digest at the selection filter. Path resolution still treats `/config` as the base in all cases.
- **Migration**: Ticked mounts become explicit selections, so existing installs keep syncing them once `include_*` stops being read as a control.
- **Docs**: Documented the sync picker - expanding folders, taking a folder wholesale or a single file, glob entry, browsable mount points, and that databases/logs/.storage are never offered for selection.
- **UI**: The Danger Zone now points to Override mode for syncing files that the security checks would block, since that control moved with the mode dropdown.

## 1.6.18

- **Feature**: The sync picker is now a real tree. Config folder and mount points expand and collapse in place, so you can dive into subfolders without losing your place, while still selecting any folder wholesale from its own row.
- **Feature**: Mount points (`/addon_configs`, `/media`, `/share`, `/ssl`, `/backup`) are browsable too, so selections can be granular - `media/photos` rather than all of `/media`.
- **Fix**: A mount root is now walked whenever any selected path lives under it. Previously a granular pick inside an un-ticked mount was silently dropped, because the root was never traversed.
- **Fix**: The `/api/sync/tree` route was bound to a helper function rather than the endpoint view, which returned raw `Path` objects and failed to serialise - the picker could not load at all.

## 1.6.17

- **Feature**: The Override warning now names exactly what is about to be published - `Publishing N selections: /config (whole folder), media ...` - and updates as you edit the selection. Override and Whitelist take the same list, so this makes the difference between them visible at the moment it matters: switching modes carries your existing selection across with the checks now off.

## 1.6.16

- **Breaking**: The built-in `esphome/*.yaml` / `zigbee2mqtt/*.yaml` allowlist is removed. It bypassed the security checks in every mode, which contradicted what the modes are for. To sync credential-bearing config, select it under **Override**.
- **Feature**: The sync mode dropdown becomes three modes, consolidated with mount points, `.gitignore` and dry run into a single **Sync Selection** section whose options change with the mode:
  - **Whitelist** - only the files/folders you select; nothing selected syncs nothing; security checks stay on
  - **Blacklist** - the default folders; security checks stay on (unchanged behaviour)
  - **Override** - only the files/folders you select; security checks off (replaces the Danger Zone checkbox)
- **Feature**: File/folder picker for `/config`, with one-click whole-config selection and glob entries such as `zigbee2mqtt/*.yaml`.
- **Hardening**: The runtime floor is explicit and absolute. Databases, WAL/SHM, logs, lockfiles, caches, `.storage`, `.git` and `node_modules` are excluded in all three modes - there is no mode that will sync them, because this add-on syncs configuration rather than backing it up. Your `.gitignore` also always wins.
- **Fix**: `.ssh` was classified as a runtime artifact while `id_rsa` was classified as a credential path, so Override could sync one but not the other. `.ssh` is now consistently a credential path.
- **Fix**: `/config/www` was walked twice, once as part of `/config` and once as its own root.
- **Migration**: Existing installs are seeded with the config root so their sync does not silently go quiet, and the Danger Zone checkbox becomes Override mode.

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