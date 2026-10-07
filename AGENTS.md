# Working on Github Config Sync

Guidance for anyone changing this repository — human or agent. User-facing
documentation lives in [`README.md`](README.md) and [`docs/`](docs/);
architecture, decisions and milestone history live in [`PROJECT.md`](PROJECT.md).

## What ships

One add-on and one version line. `addons/github-config-sync/config.yaml` is the
single source of truth for the version — `server.py` reads it at startup, and
every other place a version appears is written from it by
`scripts/sync_versions.py`.

`custom_components/github_config_sync/` is a **redirect, not an integration**.
Its config flow aborts with `addon_only`; it has no entity platforms. Do not
add features there.

## Commands

```bash
# tests — exactly what CI runs
python -m unittest discover -s addons/github-config-sync/rootfs/app/tests -v

# lint — not in CI, so run it yourself
pyflakes addons/github-config-sync/rootfs/app/*.py \
         addons/github-config-sync/rootfs/app/sync/*.py \
         addons/github-config-sync/rootfs/app/tests/*.py

# docs — CI runs this with --strict, so a broken link fails the build
mkdocs build --strict

# version propagation, then verify
python scripts/sync_versions.py --integration X.Y.Z --channel stable
python scripts/sync_versions.py --integration X.Y.Z --channel stable --check
```

CI runs tests, hassfest and the docs build. It does **not** run pyflakes and it
does **not** run `sync_versions.py --check`, so both are manual until that gap
closes (see `TODO.md`).

## Repository layout

| Path | What it is |
|---|---|
| `addons/github-config-sync/config.yaml` | version source of truth; add-on schema |
| `rootfs/app/server.py` | Flask API, scheduler, options persistence |
| `rootfs/app/sync/` | `engine.py` planning/diffing/commit · `github_client.py` rate limiting · `hashing.py` scanning and ignore rules |
| `rootfs/app/static/index.html` | the web UI — one file |
| `rootfs/app/tests/` | `unittest`, no framework beyond stdlib |
| `docs/` | GitHub Pages via mkdocs |
| `scripts/sync_versions.py` | writes the version into manifests and every version block |
| `CHANGELOG.md` | short; **this is what the HA update page reads** |
| `rootfs/app/CHANGELOG.md` | full; read by the add-on's own UI |

## Rules that exist because something went wrong

Each of these cost a real bug. They are not style preferences.

**A preview must never write state.** A dry run that rewrites the scan baseline
makes the *next* real sync agree with its own preview instead of with the
repository, so everything about to change looks already done. The same applies
to writing the repository marker: a preview that has reached GitHub has
previewed nothing. Guard the write with `if not sync_config.dry_run`, and if a
function forces live, say so in a comment — the structural test relies on that
list.

**A selection mode with nothing selected must refuse, not succeed.** Whitelist
and Override with an empty selection scan nothing and used to report
`Sync completed. Upserted 0, deleted 0`, which is byte for byte what a healthy
sync with nothing to do looks like. Refuse with a message that names the way
out. Blacklist needs no selection and must stay unaffected.

**A default is stated in many places.** The mode default lived in the Supervisor
schema (first value wins), `DEFAULT_OPTIONS`, the `SyncConfig` dataclass, four
config builders, two validators, two JavaScript fallbacks and the dropdown
order. Miss one and the server applies a mode the UI is not showing — which is
how the Layout dropdown spent months changing in the browser and never reaching
disk. Move them together and pin them with a test.

**Assert behaviour, not a constant.** The custom component carried an ignore
list nothing consumed, and the tests imported it and asserted on it — so the
suite validated a dead constant while the add-on's own lists went untested. Call
`is_ignored()`.

**An assertion that "this happened" can pin a bug as expected behaviour.** The
clean-repo test ran with `dry_run: True` and asserted the marker *was* written.
It read as coverage for years while describing the defect.

**A control that exists but is wired to nothing passes every functional
test** — nothing exercises it. When a UI control is removed or moved, assert on
the markup as well as the behaviour.

**Migration reads the repository, not the scan baseline.** A baseline only holds
what a previous sync recorded, so after a run that scanned nothing every
operation reading it became a silent no-op. Normal sync, Clean Repo and the old
Migrate Layout button all failed this way.

**`_root_map` and the walk roots are different lists.** The map keeps every root
so path resolution can answer for a mount that is not being walked; the walk
list decides what is actually hashed. Filtering one to match the other breaks
resolution.

**Out of scope is not the same as deleted.** Deleting a repository path is only
ever correct when the file is genuinely absent from disk. The migration is the
one exception, it says so, and it reads the remote tree to decide.

## Security

- Never log a token. `secrets.yaml`, `.storage`, `.cloud`, databases, logs and
  certificates are excluded and no mode re-enables the runtime floor.
- Private repositories are strongly recommended.
- Redaction lives in `_sanitized_log_tail` / `_redact_line`; diagnostics are
  masked before they leave the process.

## Releases

- Pre-release while refactoring; promote to stable once the maintainer has
  tested it on their own install.
- Bump `config.yaml`, then run `scripts/sync_versions.py` — never edit a version
  by hand, and never add a document with a version block without adding it to
  `DOC_PATHS`.
- Update all three changelogs. The root one is what the HA update page shows, so
  an unreleased-looking root changelog means users read notes for an older
  version than they are installing.
- Keep release notes free of version numbers where a reader would have to chase
  them, and say what a change *does*, not only that it changed.
