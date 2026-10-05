# Syncing

## Default ignore list

The following are excluded from sync by default:

- **HA runtime:** `.storage`, `.cloud`, `tts`, `.ha_run.lock`, `home-assistant.log`,
  `home-assistant.log.*`, `home-assistant_v2.db`, `home-assistant_v2.db-*`,
  `secrets.yaml`, `ip_bans.yaml`, `known_devices.yaml`
- **Databases:** `*.db`, `*.sqlite`, `*.sqlite3`
- **Dev/cache:** `.git`, `.cache`, `.venv`, `.vscode`, `.idea`, `.pytest_cache`,
  `.mypy_cache`, `.ruff_cache`, `__pycache__`, `.yaml_fix_backups`, `.yaml_fix_backups/*`
- **Temp/junk:** `*.tmp`, `*.swp`, `*.pyc`, `*.log`, `*.smbdelete*`, `.DS_Store`,
  `Thumbs.db`, `.ha_fix_yaml.py`

You can add extra patterns in the app UI; the resulting `.gitignore` in the
config root is now honored during scanning, so matching files are excluded
from the plan (not just skipped at upload). Live uploads also write a root
`SECURITY_UPLOAD_WARNINGS.md` file when suspicious files are skipped.

The `www` folder is not synced by default — enable the **Include www**
mount-point control to include it, with `.gitignore` patterns such as the HACS
`www/community/` subtree honored as usual.

## Clean actions

| Action | What it does |
|---|---|
| **Clean Upload** | Re-upload every local file and remove anything on the remote that is no longer local |
| **Clean Repo** | Delete only remote files that are genuinely missing from your local config, and leave everything else untouched |
| **Migrate from flat layout to structured** (tick box) | One-shot: clear the repository root so config lives only under `config/`, then grey itself out |

**Migrate from flat layout to structured** is the only one that deletes remote
paths which still exist locally, so it never runs on its own — you have to tick
it, and it is spent after one sync. Run a dry run first: it previews the exact
list of paths that would be removed and writes nothing.

The first two are destructive. The repository picker includes safety checks to
help you avoid accidentally overwriting the wrong repository.

## Repository layout

Your config directory syncs to `config/` inside the repository, and each mount
keeps its own name:

```
repo/
  config/
    configuration.yaml
    blueprints/
    custom_components/
  addon_configs/
  media/
```

Set `repo_layout: flat` in `options.yaml` to keep the config at the repository
root instead — that is how repositories synced before 1.7.2 are laid out, and
it means your config shares a namespace with the add-on's own `README.md`,
`.HA_VERSION` and `.github-config-sync-addon.json`.

Changing this does not move anything on its own. To move the files, tick
**Migrate from flat layout to structured** and run a sync (see below).

### Migrating an existing repository

Repositories synced before 1.7.2 are laid out flat, with config files sitting
at the repository root beside this add-on's own files. Tick
**Migrate from flat layout to structured** in the Danger Zone and run a sync:
the migration is performed as part of that sync's single commit, so the root is
cleared and the config is uploaded together, atomically.

- Ticking it also sets the layout to `prefixed`, because there is no longer a
  control to do that with. An un-ticked save leaves your stored layout alone —
  nothing resets behind your back.
- It removes every file at the repository root that is not under `config/` or a
  mount, **including files with no local counterpart** — the point is that the
  repository ends up mirroring your configuration, not halfway between two
  layouts.
- It deliberately keeps this add-on's own furniture: `.github-config-sync-addon.json`,
  `README.md` and `repository.yaml`.
- It is driven by the repository's own contents rather than by the scan
  baseline, so it works even after a sync that found nothing to record.
- A dry run previews it and writes nothing.

Once it has run successfully, the add-on writes
`.github-config-sync-migrated.json` to the repository root and the tick box
greys out — permanently, because the marker travels with the repository and
survives a reinstall.

## Notes

- This is **not** a zip-backup tool — files are synced individually as
  repository contents.
- The Home Assistant config folder is used automatically.
- A managed `.gitignore` is created with HA defaults plus your extra patterns.
- Keep the repository **private** if your config contains sensitive data.

## Scheduled sync

Scheduled syncs run at the selected days and `HH:MM`. Times are interpreted in
the Home Assistant host's **local timezone** (the scheduler converts UTC to host
local time), matching what you select in the UI.

## Add-on updates

The add-on's web UI checks the add-on's own GitHub repository (`/api/update-check`)
and shows when a newer build is published. Updates are installed from
Home Assistant → Add-ons → Github Config Sync → Update, not from the web UI.

The `include_pre_releases` option (default off) makes the update check also count
pre-release builds. Installations follow the single repo on `main` — the
candidate version simply lives in the add-on's `config.yaml`, so a pre-release
tag is picked up the next time the Supervisor refreshes the repository.

## Security reminders

- GitHub tokens are required for repository access and device-flow completion.
- The web UI masks stored tokens in API responses.
- If repository probing fails with an auth error, confirm the token has `repo`
  access.
- Review the app status panel and logs before enabling live syncs.

See the [Project guide](project-guide.md) for the full security posture and
the current open items.
## Safety & Liability Disclaimer

GithubConfigSync is provided as-is. By using this add-on, you acknowledge and agree that:

- **This is a configuration sync tool, not a full backup solution.** Use Home Assistant's built-in backups for restoring full system state (including databases, registries, and runtime data).
- **You assume all risks** associated with syncing your Home Assistant configuration to a Git repository, including but not limited to data loss, corruption, or unintended exposure of sensitive information.
- **The maintainer accepts no responsibility** for any data loss, credential exposure, configuration corruption, or other consequences arising from the use of this add-on, including use of any advanced/override features.
- **Overrides of recommended safety filters are strictly opt-in.** If such options are enabled, you do so entirely at your own risk and must ensure you understand the implications (especially when using public repositories).
- **Private repositories are strongly recommended** if your configuration contains any sensitive data (credentials, tokens, keys, or device identifiers). Even with private repositories, syncing sensitive files carries inherent risk.

## Sync Selection

**Settings → 5. Sync Selection** decides what gets synced. The three modes differ on two axes: how much you pick, and whether the security checks stand between you and it.

| Mode | What you pick | Security checks |
|---|---|---|
| **Blacklist** *(default)* | nothing; the default folders are walked | on |
| **Whitelist** | files and folders you select — nothing selected is **refused** | on |
| **Override** | files and folders you select | off |

- **Blacklist** *(the default)* — no selection needed, so a fresh install syncs instead of waiting for you to pick something. Walks `/config` and `/addon_configs` with the usual ignores plus the security checks; `media`, `share`, `ssl` and `backups` are opt-in and joined only if you have selected them. Community practice treats those four as things you choose to version rather than as contents of a config repository, so they are not in the default.
- **Whitelist** — select the whole configuration folder in one click, or drill down and pick individual files and folders. With nothing selected the sync **refuses** rather than reporting a success that synced nothing. The checks stay on, so a file containing a password is held back even if you selected it, and shows up in the sensitive-file report rather than vanishing silently.
- **Override** — for deliberately syncing something the checks would block, such as ESPHome or Zigbee2MQTT configs that embed wifi passwords and API keys inline. Explicitly opt-in; see the disclaimer above.

### The sync picker

**What to sync** is a tree. The configuration folder and each mount point sit at the top level, and any folder expands in place — so you can dive into `esphome/` and pick one file without losing sight of the rest.

Under the tree, **Layout** says where the configuration directory lands: everything syncs under `config/`, so it can never collide with the add-on's own `README.md`, marker or skeleton, and each mount keeps its own name. There is no longer a layout choice to make — a repository synced before 1.7.2 keeps its old shape until you tick **Migrate from flat layout to structured** and run a sync.

- **Select** on a folder takes it wholesale, recursively; **Select** on a file takes just that file.
- **`▸`** expands a folder, **`▾`** collapses it. Children load the first time you open them.
- There is no free-text path box. Every file is reachable by expanding the tree, which cannot be mistyped — a typo used to match nothing and sync zero files silently. For globs, `safe_config_paths` in `options.yaml` still works.
- Mount points are browsable too, so `media/photos` can be picked without taking all of `/media`.
- Everything selected is listed under **Selected**, with **Remove** on each row.

Selecting nothing syncs nothing. Under **Override**, the warning above the tree names exactly what will be published and updates as you edit, so the result is visible before you run.

Databases, WAL/SHM, logs, lockfiles, caches and `.storage` never appear in the tree — no mode can select them, so showing them would be misleading. Files whose *names* look credential-bearing carry a **looks sensitive** marker; that is a hint, not a block, and it is only decisive in Whitelist and Blacklist.

Regardless of mode:

- Runtime artifacts are never synced — databases, WAL/SHM files, logs, lockfiles, caches, `.storage`, `.git`, `node_modules`. No mode can re-enable them.
- Your `.gitignore` is applied last and always wins.
- Mount points outside `/config` (`addon_configs`, `media`, `share`, `ssl`, `backups`) are ticked as a group in Whitelist and Override. Blacklist always includes `addon_configs` alongside `/config` and picks up the other four only when you have selected them.

## The `.gitignore` file

The add-on reads and writes a single `.gitignore` at the root of your Home Assistant configuration directory:

```
/config/.gitignore
```

You can edit it directly, or use **Settings → Sync Selection → Recommended .gitignore entries** to write the recommended defaults. Anything matched is skipped during sync, so it is the right place to keep large or unwanted trees out of version control — for example HACS-installed integrations:

```
custom_components/
```

`.gitignore` is applied in addition to the secret filters, and still wins over the safe config path allowlist.
