# Changelog

## Migration — moving onto the structured layout

If your repository was synced before the structured layout, your config files sit at the repository root beside this add-on's own files, while the sync now writes them under `config/`. That leaves both copies until you decide otherwise — nothing is removed without you asking.

**To move across:**

1. Open the add-on and find **Migrate from flat layout to structured**, beside **Mode**.
2. Tick it.
3. Click **Sync**.

What that sync does:

- The repository root is cleared **inside that same commit** — uploads and deletions land together, so the repository is never left half-migrated.
- This add-on's own `.github-config-sync-addon.json`, `README.md` and `repository.yaml` stay at the root. Everything else there goes, including files with no local counterpart, so the repository ends up mirroring your configuration rather than sitting between two layouts.
- **Nothing is deleted from disk.** Only the repository changes.
- A dry run previews the exact list first and writes nothing.
- Afterwards `.github-config-sync-migrated.json` is written to the repository root and the tick box greys out permanently. The marker lives in the repository, so it survives an add-on reinstall.

Prefer files at the root instead? Set `repo_layout: flat` in the add-on's options file — the Layout dropdown was removed, so this is no longer a UI choice.

---

## Latest Releases

## 1.7.11

Three fixes. One of them is a behaviour change you will notice.

- **A selection mode with nothing selected now refuses instead of reporting success.** Whitelist and Override with an empty selection stop before scanning, and used to return `Sync completed. Upserted 0, deleted 0` — byte for byte what a healthy sync with nothing to do looks like. The product already refused when an empty scan had *deletions* pending; the half where nothing is pending was unguarded, so a broken selection and a quiet day were indistinguishable. It now fails with `Refusing to sync: nothing is selected`, and names the way out. Dry runs refuse too.
  **You will see this as a change:** anyone whose selection was silently empty gets a failure where they used to get a success. That is the point — the message says what to do.

- **Blacklist can actually sync `addon_configs` now.** Its path was chosen from `include_addon_configs`, which the UI derives from whether you ticked the folder — so the only way to have it synced was to select it, in the mode whose entire promise is that you select nothing. A blacklist user ticks nothing, the path became a directory that does not exist, and the walk dropped the root it had just chosen. The path is now unconditional, like `media`, `share`, `ssl` and `backups` already were, and the flag keeps only its original job of deciding whether it is walked.
  If you use Blacklist, files under `/addon_configs/<slug>/` may appear in your repository after updating.

- **Blacklist's help no longer talks about selecting.** The picker — tree and selected list alike — is hidden in that mode, so a line reading "anything else you have selected" described a state the reader could neither see nor change from where it was shown. The carry-over it referred to is real and unchanged: mounts chosen in Whitelist or Override keep syncing after a switch. That is documented in the sync docs, where it can be acted on.

- A test that raced the thread it had just cancelled no longer does, which was the intermittent suite failure.

## 1.7.10

**Stable.** This release promotes the 1.7.x line and refactors Blacklist to comply with community best practice.

- **Modes are ordered by how much they ask of you:** Blacklist (nothing to choose), Whitelist (pick what matters), Override (opt out of the checks). The first option in a Supervisor `list()` schema is the default, so ordering carries the default with it.

- **Blacklist is the new default.** Not for tidiness — it is the only mode that works with zero configuration. Whitelist with nothing selected syncs nothing *while reporting success*, so a fresh install previously sat waiting for someone to discover they had to tick something first. Now it syncs.

- **Blacklist's default folders have been refactored to comply with best practice.** It used to walk `/config`, `/addon_configs`, `/media`, `/share`, `/ssl` and `/backup` unconditionally, which meant opting into blacklist quietly put every backup, photo and certificate in your repository. It now walks **`/config` and `/addon_configs` only**; the four mounts are joined if you select them. That is how the community versions a Home Assistant configuration — [frenck's config](https://github.com/frenck/home-assistant-config/blob/master/.gitignore) ignores everything outside the config directory, [CCOSTAN's](https://github.com/CCOSTAN/Home-AssistantConfig/blob/master/.gitignore) ignores backups explicitly, and projects that do sync `/share` or `/media` sell it as a feature you turn on.

- **⚠️ Breaking if you already use Blacklist:** `media`, `share`, `ssl` and `backups` stop syncing until you select them. **Nothing is deleted** — they leave the scope of the sync and stay in your repository — but they stop updating. Select them in the tree and they resume.

- **Help text:** a note under Mode now states plainly that a mode change affects the next sync only and does not remove what is already in the repository or its history, naming Clean Repo and Reset Repo as the controls for that. The redundant Override pointer is gone from the Danger Zone, and the Layout dropdown (removed in 1.7.9) stays gone.

- A test pins every place the default is stated, because a default split across twelve sites is how the Layout dropdown spent months changing in the browser and never reaching disk. One test that had been passing vacuously — it asserted on a per-file API the batching path stopped using in 1.7.2 — now exercises the real commit.

## 1.7.9

The Layout dropdown is gone — the migration tick box takes its place.

- **One control instead of two.** Both the dropdown and the tick box answered "where do files land?", and only one answer can be true: config goes under `config/`, or the repository root still holds an older layout waiting to be cleared. The dropdown's only meaningful choice was `flat`, which is precisely what the tick box exists to move away from. It now sits beside **Mode** in the main settings, where the layout is discussed, and the Danger Zone keeps only the destructive buttons.

- **Ticking it sets the layout to `prefixed`.** Removing the last way to choose `flat` created a dead end: the tick box refused to run unless the layout was `prefixed` and told you to change a control that no longer existed. An install still sitting on `flat` could never migrate again. Ticking now implies "structured", so there is one control with one meaning.

- **Nothing resets silently.** An un-ticked save omits `repo_layout` entirely, so the server keeps whatever is stored and a plain save can never flip your layout behind your back. The option itself is untouched — it still reads, stores, defaults to `prefixed`, and remains settable in `options.yaml` if anyone wants the root layout back.

- Four tests read the markup rather than driving it: a control that exists but is wired to nothing passes every functional test, because nothing exercises it.

## 1.7.8

A small release: a sync that changes nothing no longer leaves a commit behind.

- **An idle sync no longer commits.** The repository marker was written unconditionally, and GitHub's contents API creates a commit whether or not the bytes differ — so a sync that upserted 0 files and deleted 0 still produced a `sync: add repo marker` commit, dirtying a history it had just left clean. The marker content is static, so it is now compared first and written only when it differs. Anything that cannot be compared is written rather than trusted, because a wrong marker would silently disable the migration tick box.

## 1.7.7

A one-shot way to bring an existing repository onto the structured layout — plus the bug that meant your Layout choice was never being saved.

- **New: "Migrate from flat layout to structured".** A tick box in the Danger Zone. Tick it and your next sync clears the repository root of everything that now lives under `config/`, as part of that sync's **single commit** — not a separate operation that could fail halfway and leave the two halves inconsistent. It keeps this add-on's own `.github-config-sync-addon.json`, `README.md` and `repository.yaml`, and is only available while Layout is `prefixed`. Afterwards it writes `.github-config-sync-migrated.json` to the repository root and the tick box greys out permanently. The marker lives in the repository rather than in local state, so it survives a reinstall and is visible in the repo itself.

- **The Layout dropdown has never worked.** `repo_layout` was missing from the options the UI posts, and options are replaced wholesale on every save — so the value was erased the moment you made it and the layout silently reverted to the `prefixed` default. Your repository could be restructured without anybody choosing it. A payload that omits the key now keeps what is stored rather than resetting it.

- **The migration reads the repository, not your scan baseline.** A baseline only ever records what a previous sync saw, so after a run that scanned nothing, *every* operation reading it returned an empty plan while looking successful. That is how root-level leftovers became unreachable by normal sync, Clean Repo and Migrate Layout alike. The repository is the authority on its own contents.

- **The new option reaches every config the add-on builds**, and a dry run previews the migration without writing the marker or spending the tick box.

**If you want a flat repository:** set **Layout** to `Flat` before your next sync (it now actually saves). **If you want it structured:** leave Layout on `Prefixed` and tick the migration box.
- **The `Migrate Layout` button is gone.** The tick box supersedes it, and by 1.7.7 it had become a silent no-op: it read the scan baseline, and after a run that scanned nothing the baseline held no root paths at all, so it reported success while moving nothing. Its whole job now belongs to the tick box, which reads the repository instead.

## 1.7.6

Fixes the Sync button, which was reporting success without syncing anything.

- **Manual sync ignored your selection.** `/api/sync/manual` re-created its config from a field list copied from a much older version, and four fields were dropped: `sync_paths`, `safe_config_paths`, `security_override_all_filters` and `repo_layout`. Whitelist with an empty selection scans nothing, so every manual sync returned `Sync completed. Upserted 0, deleted 0` for a run that touched no files. Nothing reported an error, because the engine was doing exactly what it had been told - just told nothing. The scheduled sync does not rebuild, which is why the 03:00 run kept committing and made the fault look intermittent rather than total.

- **Clean Upload carried the same copy and is worse for it.** It forces `dry_run` off to do real work, and dropping `repo_layout` alongside it meant a flat repository would have staged files under `config/` beside the ones already at the root - an active corruption of a working repository rather than a silent no-op.

- Both rebuilds are gone. Three tests now pin it shut: any config construction outside the two builders must carry the selection fields, and neither endpoint may re-create the config. A fourth posts to the endpoint the Sync button actually calls and asserts a selected file reaches the plan - every existing sync test posted to a different endpoint, which is why 250 tests passed throughout.

**Upgrading from 1.7.1 or earlier:** repositories synced before 1.7.2 are laid out flat, but `repo_layout` now defaults to `prefixed`. Tick **Migrate from flat layout to structured** and sync once to move onto the new layout, or set `repo_layout: flat` in the add-on's options file to keep files at the root. Until you choose, both copies coexist - nothing is deleted.

## 1.7.5

Fixes the cause of a sync that hangs while reporting itself as running.

- **One client's rate limit could stall every other client.** The backoff state was module-global, so any request that drew a rate limit made *every* GitHub client in the process wait on it - including clients that had hit no limit of their own and could not have cleared it.

- **In practice the add-on was stalling itself.** Its update check runs unauthenticated, because it reads the add-on's public repository and so cannot use your token. Unauthenticated requests share GitHub's much smaller 60/hour per-IP budget. When that was spent, the update check opened a backoff of roughly half an hour, and authenticated syncs queued behind it - reporting "running", waiting on a limit they had not hit. The 403 body says so outright: *"API rate limit exceeded... Authenticated requests get a higher rate limit."*

- The backoff state now belongs to each client. The update check additionally gives up on a rate limit rather than sleeping through one - it is optional work, its caller caches the failure and carries on, and nothing is gained by parking it for half an hour. Syncs that hit a real limit still back off and retry exactly as before.

  This should be the last of the rate-limit work. 1.7.3 capped the retry loop and made sure a sync always clears its gate; this removes the reason the gate was opening at all.

## 1.7.4

Fixes 1.7.3's own logging, which never reached the log.

- **The sync lifecycle lines added in 1.7.3 were discarded.** The app configured no logging at all - it silenced `werkzeug` and left the rest to Python's fallback handler, which emits `WARNING` and above only. The start and finish lines are `INFO`, so they were dropped before reaching the add-on log. A sync that started and finished cleanly was therefore indistinguishable in the log from one that never started, which is precisely the ambiguity 1.7.3 set out to remove. The entrypoint now enables `INFO`; `werkzeug` stays silenced so per-request logging does not appear.

## 1.7.3

Fixes a sync that reports itself as running and then does nothing.

### The stuck-sync cause

- **The rate-limit gate outlived the sync that opened it.** The gate is module-global and cleared only as time passed over - `reset_rate_limit_gate()` was called from tests and nowhere else, despite its own docstring saying it was used "after a sync finishes". A sync that was cancelled, or that gave up, left the gate open, and the next run then sat waiting on a gate belonging to a sync that had already finished: status "running", no requests, no progress, no way out but restarting the add-on. Every sync now clears the gate when it ends, whether it succeeded, failed or was cancelled.

### Bounded, diagnosable rate limiting

- **A rate limit that does not clear now fails instead of retrying forever.** The request loop had no attempt ceiling, so a permanently refused request retried for hours - no error, no result, repository untouched, and nothing in the log saying why. It now honours the wait GitHub asks for, three times, then raises a real error. Failing visibly after the wait was requested is deliberate: giving up sooner would break syncs that only needed to pause.
- **GitHub's own explanation is logged and carried into the error.** The 403 body was discarded, so an exhausted quota was indistinguishable from a token that cannot reach the repository - and those need opposite fixes. One truncated line now settles it.
- **Waiters are no longer released in lockstep.** When the gate cleared, every waiting thread fired at GitHub simultaneously, which is what draws a secondary rate limit; that re-armed the gate and repeated indefinitely, so the backoff could not converge. Each thread now waits the gate out and then adds a short offset of its own.
- **Syncs are logged.** There were no log calls at all in the sync engine or server, so a sync that started, ran, succeeded or failed produced no output whatsoever - the add-on's entire job was invisible in its own log. Start, outcome, counts and duration are now recorded, and a failure is logged with its reason.

## 1.7.2

Prefixed repository layout, a size cap, and selection by picking only.

### Repository layout

Your config directory now goes to `config/` inside the repository, and each mount keeps its own name - so `media/`, `addon_configs/`, `share/`, `ssl/` and `backups/` are unchanged:

```
repo/
  config/
    configuration.yaml
    blueprints/
    custom_components/
  addon_configs/
  media/
```

Flat layout put `configuration.yaml` at the repository root, in the same namespace as the add-on's own `README.md`, `.HA_VERSION` and `.github-config-sync-addon.json`. Either could have overwritten the other. **`prefixed` is the default.** `flat` is still available in Sync Selection for repositories that want the old shape.

- **Existing repositories are not changed by upgrading.** Switching layout alone moves nothing: the scanner only sees `config/...` keys afterwards, and 1.7.1's out-of-scope rule correctly leaves the old root paths alone rather than deleting files that are still on disk.
- **New: Migrate Layout, in the Danger Zone.** It moves the old root files under `config/` and removes the emptied root paths. It is the only operation that deletes remote paths which still exist locally, so it is never automatic: run a dry run first to see the list, confirm, and it reports by name anything it left in place or skipped because `config/` already had that file. A dry run does not move the baseline.

### One commit per run

- **A sync is now a single commit instead of one commit per file.** Per-file commits cost three API calls a file - fetch the SHA, write the content, write the commit - so a 224-file repository needed over 600 calls. That is what drove the rate-limit backoff loop, and a run that failed partway left the repository in a state matching no plan the user had been shown. Staging blobs and writing one tree, one commit and one ref update makes it N+3, and the run is now atomic: either the whole change lands or none of it does. Deletions are staged in that same commit.
- **A concurrent push is no longer overwritten.** The branch ref is updated without force, so if someone pushes while the run is staging, the run rebuilds on the new head instead of discarding their commit. Blobs are content-addressed, so the retry re-uploads nothing.
- **The executable bit is preserved**, which the per-file API used to lose.
- Cancelling mid-run now leaves the repository exactly as it was, rather than partially updated.

### Files GitHub will not accept

- **A file larger than 50 MB is skipped and listed by name.** GitHub answers a 422 for these, and that error aborted the whole run - so one archive another add-on had written into the config directory cost every other file in the sync. They are skipped in the plan, the run message and the UI, because a silent skip is indistinguishable from a file that never existed. **Clean Repo protects them too**: deleting a file the sync can no longer upload would destroy the only copy.
- `.gitignore` is now honoured from the config root, so `*.tar.gz` and similar keep large artifacts out of the scan.

### Selection

- **The free-text path box is removed.** It accepted anything and a typo matched nothing - which is how `/config` came to mean the literal folder `config` and synced zero files. Every file is reachable by expanding the tree, which cannot be mistyped. `safe_config_paths` remains as the config-file-only escape hatch for globs.


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

- **Docs**: Added a Safety & Liability Disclaimer to the documentation clarifying that this is a configuration sync tool (not a full backup), users assume all risks, and the maintainer accepts no responsibility for data loss/credential exposure or consequences of using override features.

## 1.6.11

- **Chore**: The Stable/Dev version pills are removed from the header and the stale `repo_versions` payload is dropped from `/api/health` and `/api/status` — they only ever echoed the installed version. The add-on update badge is now the one place the version shows: "Up to date: v1.6.x" or "Update available: v1.6.10" (with the candidate tag, pre-release included when the toggle is on)

## 1.6.10

- **Chore**: The "Installed / Latest / Latest stable / Available" detail line is removed from the add-on updates section. The updates panel now shows just the status badge and the "Show pre-release build updates" toggle — installing a pre-release build is done from Home Assistant &rarr; Add-ons, and the toggle is what makes pre-release builds appear there as candidates

## 1.6.9

- **Reliability**: New rate-limit watchdog. GitHub `429` and secondary/abuse limits are now retried until they clear (or the sync is cancelled) instead of failing after 5 attempts — the wait honours `Retry-After` / `X-RateLimit-Reset` headers, a shared gate makes every concurrent upload/delete worker hold together so the batch doesn't stampede the API, waiting can be cancelled at any time, and the UI shows "waiting" progress instead of freezing mid-sync
- **Reliability**: The core rate-limit budget is watched as well: when nearly exhausted the engine pauses before sending rather than burning requests on guaranteed `403`s
- **Fix**: The "Show pre-release build updates" and sync-mode controls were missing from the form's auto-save listener list, so changing either on its own never saved — the toggle snapped back on the next reload or tab-return. Both are now wired to auto-save like every other option
- **Test**: 429/Retry-After backoff and waits, retries past the old 5-attempt cap until success, cancel-during-wait aborts, and cancelled rate-limit waits surface as a cancelled sync instead of a failure

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
