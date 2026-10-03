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
| **Clean Upload** | Force a full re-upload and remove remote extras |
| **Clean Repo** | Wipe the remote repo and restore starter files in one step |

Both are destructive. The repository picker includes safety checks to help you
avoid accidentally overwriting the wrong repository.

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
