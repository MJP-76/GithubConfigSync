# Github Config Sync

[![Documentation][badge-docs]][docs]
[![Home Assistant][badge-home-assistant]][home-assistant]
[![HACS][badge-hacs]][hacs]
[![HACS Validation][badge-hacs-validation]][workflow-hacs-validation]
[![Hassfest][badge-hassfest]][workflow-hassfest]
[![CI][badge-ci]][workflow-ci]
[![Release][badge-release]][releases]
[![Built with AI][badge-built-with-ai]][built-with-ai]

Home Assistant **add-on** for syncing your config folder to GitHub. This is a config sync tool, not a backup tool.

**Private repositories are strongly recommended.** Use caution with public repos and any two-way sync tools that also write to your Home Assistant config tree — they can cause local config loss or unexpected deletions.

<!-- VERSION:START -->
- Integration version: `1.7.11`
- Add-on version: `1.7.11`
- Channel: `stable`
- Release tag: `v1.7.11`
<!-- VERSION:END -->

## Support me

If you find this project useful, and would like to help support its continued development, you can do so here:

[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-FFDD00?style=for-the-badge&logo=buymeacoffee&logoColor=000000)](https://www.buymeacoffee.com/mjp76)
[![Ko-fi](https://img.shields.io/badge/Ko--fi-F16061?style=for-the-badge&logo=ko-fi&logoColor=ffffff)](https://ko-fi.com/mjp76)
[![Octopus Energy — you get £50, I get £50](https://img.shields.io/badge/Octopus%20Energy-%E2%80%94%20you%20get%20%C2%A350%2C%20I%20get%20%C2%A350-14294A?style=for-the-badge&logo=octopus-energy&logoColor=ffffff)](https://share.octopus.energy/iron-moose-196)

## Features

- GitHub OAuth Device Flow login (approve on github.com)
- Create a new repository or use an existing one
- Sync your Home Assistant config folder to GitHub
- Auto-generate a Home Assistant-friendly `.gitignore`
- Customizable ignore patterns
- Manual sync button in Home Assistant
- Scheduled syncs (day-of-week + time-of-day selection)
- Optional dated GitHub release creation before each sync
- Clean Upload — force full re-upload and remove remote extras
- Clean Repo — delete only remote files genuinely missing from your local config
- Migrate from flat layout to structured — one-shot: clear the repository root so config lives only under `config/`, then grey itself out
- Prefixed repository layout by default, so your config never shares a namespace with the add-on's own files
- Repository picker with safety checks to avoid accidental overwrites
- Sensitive-file scanning and reporting

## Installation

> **This is a Home Assistant add-on, not a HACS integration.** Install it from the Add-on Store.

1. In Home Assistant, open **Settings → Add-ons → Add-on Store → Repositories**.
2. Add this repository URL: `https://github.com/MJP-76/GithubConfigSync`.
3. Install **Github Config Sync** and start it.
4. Open the app web UI (ingress), configure repository settings, and complete GitHub Device Flow login.

## Getting Started

1. Open the app UI from the Add-on page.
2. Complete GitHub Device Flow login.
3. Pick an existing repository or create a new one.
4. Run a dry run first to confirm the scan looks correct.
5. Switch to a live run when ready.

## Default Ignore List

The following are excluded from sync by default:

- **HA runtime:** `.storage`, `.cloud`, `tts`, `.ha_run.lock`, `home-assistant.log`, `home-assistant.log.*`, `home-assistant_v2.db`, `home-assistant_v2.db-*`, `secrets.yaml`, `ip_bans.yaml`, `known_devices.yaml`
- **Databases:** `*.db`, `*.sqlite`, `*.sqlite3`
- **Dev/cache:** `.git`, `.cache`, `.venv`, `.vscode`, `.idea`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `__pycache__`, `.yaml_fix_backups`, `.yaml_fix_backups/*`
- **Temp/junk:** `*.tmp`, `*.swp`, `*.pyc`, `*.log`, `*.smbdelete*`, `.DS_Store`, `Thumbs.db`, `.ha_fix_yaml.py`

You can add extra patterns in the app UI. Live uploads also write a root `SECURITY_UPLOAD_WARNINGS.md` file when suspicious files are skipped.

## Notes

- This is not a zip-backup tool — files are synced individually as repository contents.
- The Home Assistant config folder is used automatically.
- A managed `.gitignore` is created with HA defaults and your extra patterns.
- Keep the repository private if your config contains sensitive data.
- After a release, Home Assistant may need a rebuild/reinstall to pick up UI changes from the add-on image.

## Development

Development happens on [`main`](https://github.com/MJP-76/GithubConfigSync). There is one
version line and releases are cut from it.

The release workflow, architecture and milestone history live in
[PROJECT.md](PROJECT.md). What is planned next lives in [TODO.md](TODO.md), and the
changes themselves in [CHANGELOG.md](CHANGELOG.md).

## Migration

Repositories synced before the structured layout have configuration files at the
repository root, alongside this add-on's own files. One tick moves them under
`config/`:

1. Find **Migrate from flat layout to structured**, beside **Mode**.
2. Tick it.
3. Click **Sync**.

The root is cleared **inside that sync's single commit**, so uploads and
deletions land together and the repository is never left half-migrated. This
add-on's `.github-config-sync-addon.json`, `README.md` and `repository.yaml`
stay; files with no local counterpart go; and **nothing is deleted from disk** —
only the repository changes. A dry run previews the exact list first.

Afterwards `.github-config-sync-migrated.json` is written to the repository root
and the tick box greys out permanently. The marker lives in the repository, so it
survives a reinstall. Prefer files at the root? Set `repo_layout: flat` in the
add-on's options file.

## Documentation

- **[Project Guide](PROJECT.md)** — architecture, security, milestones, and release workflow.
- **[Changelog](CHANGELOG.md)** — release history.

[badge-docs]: https://img.shields.io/badge/Documentation-41BDF5?style=flat-square&logo=bookstack&logoColor=white
[docs]: https://MJP-76.github.io/GithubConfigSync/
[badge-home-assistant]: https://img.shields.io/badge/Home%20Assistant-41BDF5?style=flat-square&logo=homeassistant&logoColor=white
[home-assistant]: https://www.home-assistant.io/
[badge-hacs]: https://img.shields.io/badge/HACS-Custom-41BDF5.svg
[hacs]: https://github.com/hacs/integration
[badge-hacs-validation]: https://img.shields.io/badge/HACS%20Validation-passing-brightgreen
[workflow-hacs-validation]: https://github.com/MJP-76/GithubConfigSync/actions/workflows/validate.yml
[badge-hassfest]: https://img.shields.io/github/actions/workflow/status/MJP-76/GithubConfigSync/hassfest.yml?branch=main&label=Hassfest
[workflow-hassfest]: https://github.com/MJP-76/GithubConfigSync/actions/workflows/hassfest.yml
[badge-ci]: https://github.com/MJP-76/GithubConfigSync/actions/workflows/ci.yml/badge.svg
[workflow-ci]: https://github.com/MJP-76/GithubConfigSync/actions/workflows/ci.yml
[badge-release]: https://img.shields.io/github/v/release/MJP-76/GithubConfigSync?style=flat&label=Release
[releases]: https://github.com/MJP-76/GithubConfigSync/releases
[badge-built-with-ai]: https://img.shields.io/badge/Built%20with-AI-black?logo=openai&logoColor=white
[built-with-ai]: https://openai.com

## Safety & Liability Disclaimer

GithubConfigSync is provided as-is. By using this add-on, you acknowledge and agree that:

- **This is a configuration sync tool, not a full backup solution.** Use Home Assistant's built-in backups for restoring full system state (including databases, registries, and runtime data).
- **You assume all risks** associated with syncing your Home Assistant configuration to a Git repository, including but not limited to data loss, corruption, or unintended exposure of sensitive information.
- **The maintainer accepts no responsibility** for any data loss, credential exposure, configuration corruption, or other consequences arising from the use of this add-on, including use of any advanced/override features.
- **Overrides of recommended safety filters are strictly opt-in.** If such options are enabled, you do so entirely at your own risk and must ensure you understand the implications (especially when using public repositories).
- **Private repositories are strongly recommended** if your configuration contains any sensitive data (credentials, tokens, keys, or device identifiers). Even with private repositories, syncing sensitive files carries inherent risk.

### Sync Selection

**Settings → 5. Sync Selection** is where you decide what gets synced. The three modes differ on two axes: how much you pick, and whether the security checks stand between you and it.

| Mode | What you pick | Security checks |
|---|---|---|
| **Blacklist** *(default)* | nothing; the default folders are walked | on |
| **Whitelist** | files and folders you select — nothing selected is **refused** | on |
| **Override** | files and folders you select | off |

- **Blacklist** *(the default)* — no selection needed, so a fresh install syncs instead of waiting for you to pick something. Walks `/config` and `/addon_configs` with the usual ignores plus the security checks; `media`, `share`, `ssl` and `backups` are opt-in and joined only if you have selected them. The closest thing to "sync my config, don't think about it".
- **Whitelist** — for when you know exactly what you want tracked. With nothing selected the sync **refuses** rather than reporting a success that synced nothing. Select the whole configuration folder in one click, or drill down and pick individual files and folders. The checks stay on, so a file containing a password is held back even if you selected it; it appears in the sensitive-file report instead of vanishing silently.
- **Override** — for deliberately syncing something the checks would block. ESPHome and Zigbee2MQTT configs embed wifi passwords and API keys inline, so this is how those get version-controlled. Explicitly opt-in and carries the risks set out in the disclaimer below.

#### The sync picker

**What to sync** is a tree. The configuration folder and each mount point sit at the top level, and any folder expands in place — so you can dive into `esphome/` and pick one file without losing sight of the rest.

Under the tree, **Layout** says where the configuration directory lands: everything syncs under `config/`, so it can never collide with the add-on's own `README.md`, marker or skeleton, and each mount keeps its own name. There is no longer a layout choice to make — a repository synced before 1.7.2 keeps its old shape until you tick **Migrate from flat layout to structured** and run a sync. That one-shot migration clears the repository root of everything that now lives under `config/`, keeps this add-on's own marker, `README.md` and `repository.yaml`, then writes `.github-config-sync-migrated.json` and greys the tick box out.

- **Select** on a folder takes it wholesale, recursively; **Select** on a file takes just that file.
- **`▸`** expands a folder, **`▾`** collapses it. Children load the first time you open them.
- There is no free-text path box. Every file is reachable by expanding the tree, which cannot be mistyped — a typo used to match nothing and sync zero files silently. For globs, `safe_config_paths` in `options.yaml` still works.
- Mount points are browsable too, so `media/photos` can be picked without taking all of `/media`.
- Everything selected is listed under **Selected**, with **Remove** on each row.

Selecting nothing syncs nothing. Under **Override**, the warning above the tree names exactly what will be published and updates as you edit, so the result is visible before you run.

Databases, WAL/SHM, logs, lockfiles, caches and `.storage` never appear in the tree — no mode can select them, so showing them would be misleading. Files whose *names* look credential-bearing carry a **looks sensitive** marker; that is a hint, not a block, and it is only decisive in Whitelist and Blacklist.

In every mode:

- **Runtime artifacts are never synced** — databases, WAL/SHM files, logs, lockfiles, caches, `.storage`, `.git` and `node_modules`. This add-on syncs configuration, not system state, and no mode will pull those in.
- **Your `.gitignore` always wins.**
- Mount points outside `/config` (`addon_configs`, `media`, `share`, `ssl`, `backups`) are ticked as a group in Whitelist and Override. Blacklist always includes `addon_configs` alongside `/config` and picks up the other four only when you have selected them.

### The `.gitignore` file

The add-on reads and writes a single `.gitignore` at the root of your Home Assistant configuration directory:

```
/config/.gitignore
```

Create it with the File Editor add-on under `config`, or via the add-on's own **Settings → Sync Selection → Recommended .gitignore entries** section, which can write the recommended defaults for you. Use it to keep things you do not want under version control — for example `custom_components/`, which mostly holds HACS-installed integrations:

```
custom_components/
```

Anything matched there is skipped during sync. Note this is separate from the secret filters above: `.gitignore` is your choice, the secret filters are the add-on's safety net.
