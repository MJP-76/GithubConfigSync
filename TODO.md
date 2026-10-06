# GitHub Config Sync — TODO

Our own list of things we want to do. GitHub Issues stay the source of truth
for bugs; this file is for work that is not a bug report. An item may name an
issue as the target of the work, but must not restate or mirror what the issue
says.

---

## Correctness

- [ ] **Clean Repo writes state on a dry run**

      `_save_json(HASH_INDEX_PATH, ...)` and `_ensure_repo_marker()` sit outside
      the `if not sync_config.dry_run:` guard in `trigger_clean_repo`, so a
      preview replaces the scan baseline and can write the repository marker.
      Same bug class as the `/api/sync` dry run, which was fixed; this path was
      not in that pass.

- [ ] **Serialise manual syncs against the scheduler**

      The scheduler guards its own runs with `_running`, but a manual sync does
      not consult it, so a click can overlap a scheduled run.

- [ ] **Delete confirmation should name the files**

      Clean Upload, Clean Repo and Reset Repo confirm what they do but not what
      they will remove. The standing rule is filenames, never a count.

- [ ] **Investigate the unexplained `0 oversized`**

      A sync at 19:35 UTC reported `0 oversized` where every reproduction —
      both layouts, all three modes — reports `1`. Reporting only: the database
      is excluded from the index by the security floor regardless, so nothing
      was ever at risk. Unresolved rather than understood.

- [ ] **Decide the `deps/` and `opencode/` exclusions**

      Neither is in `IGNORE_DIRS`, `SECURITY_DIRS` or `RUNTIME_PATTERNS`, so
      `opencode/` syncs. Unanswered.

## Product

- [ ] **Follow `!include` references so a selection is self-contained**

      Picking a file that `!include`s another should imply the included one —
      shown as *implied* in the tree rather than as a separate tick.

      Today, removing an included file from the selection deletes it from the
      repository even though something still references it.

      Constraints: must not bypass the runtime floor, the security checks, or
      the user's `.gitignore`.

      Surfaced in the #44 thread and committed to there as "looking at adding".

- [ ] **Fold the migration marker into the sync commit**

      The migration and the `.github-config-sync-migrated.json` marker are two
      commits. The marker is written after the main commit lands, deliberately —
      a failed migration must not spend the tick box — but it could be staged
      into the same tree instead, giving one commit and keeping that ordering.

## Housekeeping

- [ ] **Refresh PROJECT.md**

      It calls itself the single source of truth and currently says version
      `1.6.0`, says the `-dev` repository is decommissioned (it is not — it is
      the live sync target), and is dated 2026-08-07.

- [ ] **Open issues to work through** — #36, #30, #8
