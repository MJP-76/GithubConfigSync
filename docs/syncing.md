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

You can add extra patterns in the app UI. Live uploads also write a root
`SECURITY_UPLOAD_WARNINGS.md` file when suspicious files are skipped.

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

## Security reminders

- GitHub tokens are required for repository access and device-flow completion.
- The web UI masks stored tokens in API responses.
- If repository probing fails with an auth error, confirm the token has `repo`
  access.
- Review the app status panel and logs before enabling live syncs.

See the [Project guide](project-guide.md) for the full security posture and
the current open items.