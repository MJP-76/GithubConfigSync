from __future__ import annotations

import fnmatch
import logging
import time
from pathlib import Path
from typing import Callable

from .errors import SyncError
from .github_client import ADDON_REPO_MARKER_PATH, GitHubClient, MIGRATED_MARKER_PATH

_LOGGER = logging.getLogger(__name__)
from .hashing import GitIgnoreMatcher, build_hash_index, diff_hash_indexes, scan_sensitive_files
from .models import SyncConfig, SyncPlan, SyncResult

# The three sync modes. Each is a preset over one question: how much do you
# pick, and do the security checks stand between you and it.
#
#   whitelist - you pick the paths; the security checks still apply
#   blacklist - the default folders; the security checks still apply
#   override  - you pick the paths; the security checks stand aside
#
# The runtime floor (databases, WAL/SHM, logs, locks, caches, .storage) and the
# user's own .gitignore are outside that question: no mode re-enables them.
SYNC_MODE_WHITELIST = "whitelist"
SYNC_MODE_BLACKLIST = "blacklist"
SYNC_MODE_OVERRIDE = "override"
SYNC_MODES = (SYNC_MODE_WHITELIST, SYNC_MODE_BLACKLIST, SYNC_MODE_OVERRIDE)

# Modes in which sync_paths is consulted. Blacklist syncs the defaults and
# deliberately does not consult the selection.
SELECTION_MODES = (SYNC_MODE_WHITELIST, SYNC_MODE_OVERRIDE)

# Mounts that live outside the config directory and are selected by name.
MOUNT_KEYS = ("addon_configs", "media", "share", "ssl", "backups")

# Blacklist's default folders: the add-on configuration directory. The
# configuration root is covered by _root_enabled, which returns True for it.
#
# media, share, ssl and backups are deliberately not here. Versioning them is
# an opt-in - community practice treats them as things you choose to sync, not
# as contents of a config repository - and a config repo that quietly grew a
# copy of every backup and photo is a worse default than one that needs a tick
# to include them.
BLACKLIST_DEFAULT_ROOTS = frozenset({"addon_configs"})

# The selection entry meaning "everything under /config". Stored as "." because
# an empty string would otherwise silently mean "everything".
WHOLE_CONFIG_ROOT = "."

# The add-on's own furniture at the repository root. A migration makes the
# repository mirror /config under config/, but these belong to the add-on, not
# to the configuration - deleting them would break the marker check and lose
# the skeleton that a reset restores.
MIGRATION_KEEP_AT_ROOT = frozenset(
    {ADDON_REPO_MARKER_PATH, "README.md", "repository.yaml", MIGRATED_MARKER_PATH}
)
# Filesystem name of the config directory. Selections are repo-relative, so a
# leading "/config" on an absolute path is stripped rather than searched for.
CONFIG_ROOT_NAME = "config"


def _mount_prefix(key: str) -> str:
    head = key.split("/", 1)[0]
    return head if head in MOUNT_KEYS else ""


def _normalise_selection(raw: object) -> str | None:
    """Normalise one selection entry, or None to drop it.

    The picker labels roots the way the filesystem does - /config, /media,
    /addon_configs - while selection keys are repo-relative. A leading root
    name on an absolute path is therefore stripped instead of being left to
    match nothing: /config came to mean the literal folder "config" and
    selected none of the files it was meant to cover.

    Only absolute paths are rewritten, so a relative "media" folder inside the
    config directory keeps meaning that folder.
    """
    value = str(raw or "").strip().replace("\\", "/")
    absolute = value.startswith("/")
    while value.startswith("./"):
        value = value[2:]
    value = value.strip("/")
    if not value:
        return None
    if value == WHOLE_CONFIG_ROOT:
        return WHOLE_CONFIG_ROOT
    if absolute:
        head, _, tail = value.partition("/")
        if head == CONFIG_ROOT_NAME:
            return tail or WHOLE_CONFIG_ROOT
        if head in MOUNT_KEYS:
            # Mount paths keep their prefix in the index, unlike config paths.
            return f"{head}/{tail}" if tail else head
    return value


def _selection_matches(selection: str, key: str) -> bool:
    """Whether a selection entry covers a repo-relative key.

    Directory selections are recursive, and a bare ``*`` in an entry is treated
    as a glob so ``zigbee2mqtt/*.yaml`` selects only those files.
    """
    if selection == WHOLE_CONFIG_ROOT:
        return _mount_prefix(key) == ""
    if fnmatch.fnmatchcase(key, selection):
        return True
    prefix = selection.rstrip("/")
    return key == prefix or key.startswith(prefix + "/")


class SyncEngine:
    def __init__(self, config: SyncConfig, previous_hash_index: dict[str, str]) -> None:
        self._config = config
        self._previous_hash_index = previous_hash_index
        self._config_root = Path(config.config_root)
        addon_config_root = getattr(config, "addon_config_root", "/addon_configs")
        self._addon_config_root = Path(addon_config_root) if addon_config_root else Path("/__missing_addon_configs__")
        # The config root's prefix is what decides whether its files land at the
        # repository root or under config/. It was always "", which is why the
        # config shared a namespace with the add-on's own README and marker.
        config_prefix = "" if getattr(config, "repo_layout", "prefixed") == "flat" else "config"
        self._config_prefix = config_prefix
        self._root_map = [
            (config_prefix, self._config_root),
            ("addon_configs", self._addon_config_root),
            ("media", Path("/media")),
            ("share", Path("/share")),
            ("ssl", Path("/ssl")),
            ("backups", Path("/backup")),
        ]
        # "www" is deliberately not a separate root: it lives inside the config
        # directory, so listing it walked every file under it a second time.
        # Kept unfiltered: telling "out of scope" apart from "deleted" has to
        # consider every root, including ones this selection never walks.
        self._all_roots = list(self._root_map)
        self._selections = self._build_selections()
        if self._config.sync_mode in SELECTION_MODES:
            self._root_map = [
                item
                for item in self._root_map
                if self._is_config_root(item[0]) or self._root_needed(item[0])
            ]
        self._github = GitHubClient(
            repository=config.repository,
            branch=config.branch,
            token=config.token,
        )
        self._sensitive_files: list[str] = []
        self._oversized: list[str] = []
        self._cancel_requested: Callable[[], bool] = lambda: False
        self._progress_callback: Callable[[dict[str, object]], None] = lambda _payload: None
        self._last_progress: dict[str, object] = {}
        # Set only by plan(), so a run driven by clean_plan() - which never
        # computes migration removals - cannot write the marker and grey the
        # tick box out with the repository still un-migrated.
        self._migration_applied = False

    def set_cancel_checker(self, cancel_requested: Callable[[], bool]) -> None:
        self._cancel_requested = cancel_requested
        self._wire_rate_limit_watchdog()

    def set_progress_callback(self, progress_callback: Callable[[dict[str, object]], None]) -> None:
        def _track(payload: dict[str, object]) -> None:
            self._last_progress = dict(payload)
            progress_callback(payload)

        self._progress_callback = _track
        self._wire_rate_limit_watchdog()

    def _wire_rate_limit_watchdog(self) -> None:
        """Keep the GitHub client's rate-limit watchdog pointed at this sync.

        While GitHub is rate-limiting, every in-flight upload/delete sleeps in
        the client until the limit clears and then retries — the watchdog only
        needs to know how to cancel those waits and how to surface a "waiting"
        progress payload so the UI shows the pause instead of a frozen bar.
        """
        self._github.register_rate_limit_hooks(
            cancel_check=self._cancel_requested,
            progress=self._report_rate_limit_wait,
        )

    def _report_rate_limit_wait(self, info: dict[str, object]) -> None:
        wait = info.get("wait_seconds")
        reason = info.get("reason") or "rate limited"
        wait_text = f"~{wait:.0f}s" if isinstance(wait, (int, float)) else "a few seconds"
        payload = dict(self._last_progress)
        payload.update(
            {
                "status": "running",
                "current_action": "waiting",
                "current_path": f"GitHub rate limit ({reason}) — retrying in {wait_text}",
            }
        )
        self._progress_callback(payload)

    def probe_repository(self) -> tuple[bool, str]:
        return self._github.probe_repository()

    def plan(self) -> tuple[SyncPlan, dict[str, str]]:
        current_hash_index = self._build_hash_index()
        added, changed, removed = diff_hash_indexes(self._previous_hash_index, current_hash_index)
        removed_paths = self._genuinely_gone(removed)
        if self._config.migrate_layout:
            self._migration_applied = True
            # Deliberately outside _genuinely_gone: a migration clears paths
            # whose local copy very much still exists, which is the one case
            # where a remote path with a live file behind it should go.
            removed_paths = sorted(
                set(removed_paths)
                | set(self._migration_removals(self._github.list_all_paths()))
            )
        plan = SyncPlan(
            added=added,
            changed=changed,
            removed=removed_paths,
            total_files=len(current_hash_index),
            oversized=list(self._oversized),
        )
        return plan, current_hash_index

    def _migration_removals(self, remote_paths: list[str]) -> list[str]:
        """Repository-root paths a migration should clear.

        Driven by the remote tree, not the scan baseline. A baseline only ever
        holds what a previous sync recorded, so after a run that scanned
        nothing it holds nothing - and every other operation reading it becomes
        a silent no-op. The repository itself is the authority on what it
        contains.
        """
        if not self._config_prefix:
            raise SyncError(
                "Migration only applies to the prefixed layout. Set Layout to "
                "Prefixed first - config files must land under config/ before "
                "the repository root can be cleared."
            )
        # Anything under config/ or a mount is already where it belongs.
        structured = {self._config_prefix, *MOUNT_KEYS}
        return sorted(
            path
            for path in remote_paths
            if path not in MIGRATION_KEEP_AT_ROOT
            and path.split("/", 1)[0] not in structured
        )

    def clean_plan(self) -> tuple[SyncPlan, dict[str, str]]:
        current_hash_index = self._build_hash_index()
        all_paths = sorted(current_hash_index.keys())
        # A file skipped for being too large is missing from the scan but not
        # gone from disk. Deleting it here would destroy the only copy there
        # is, because no later sync could upload it either.
        protected = set(self._oversized)
        removed_paths = sorted(
            path
            for path in self._previous_hash_index
            if path not in current_hash_index and path not in protected
        )
        plan = SyncPlan(
            added=all_paths,
            changed=[],
            removed=removed_paths,
            total_files=len(current_hash_index),
            oversized=list(self._oversized),
        )
        return plan, current_hash_index

    def run(self, plan: SyncPlan) -> SyncResult:
        """Apply a plan, logging the outcome and always clearing the rate gate.

        The gate is module-global and otherwise only clears as time passes, so
        a run that was cancelled or that gave up after the retry ceiling left it
        open. The next run - including a manual one - then sat waiting on a gate
        from a sync that had already finished, reporting itself as running while
        doing nothing.

        Logging here rather than inside the body means the dry run, the cancel
        path and the failure path are all covered by one place, and a sync that
        starts, succeeds or fails is visible in the add-on log at all.
        """
        started = time.monotonic()
        upsert_paths = [*plan.added, *plan.changed]
        removed_paths = list(plan.removed)
        _LOGGER.info(
            "Sync starting (%s) for %s@%s: %d file(s) in scope, "
            "%d to upsert, %d to delete, %d oversized",
            "dry run" if self._config.dry_run else "live",
            self._config.repository,
            self._config.branch,
            plan.total_files,
            len(upsert_paths),
            len(removed_paths),
            len(plan.oversized),
        )
        try:
            result = self._run_plan(plan, upsert_paths, removed_paths)
        except Exception as err:
            _LOGGER.error(
                "Sync failed after %.1fs for %s: %s: %s",
                time.monotonic() - started,
                self._config.repository,
                type(err).__name__,
                err,
            )
            raise
        finally:
            # Never leave a stale gate behind for the next run to wait on.
            self._github.reset_rate_gate()
        if self._migration_applied and not self._config.dry_run:
            try:
                self._github.write_migrated_marker()
            except SyncError as err:
                # The migration itself landed. Failing the run because the
                # marker could not be written would make a successful
                # migration read as a failure - the tick box simply stays on.
                _LOGGER.warning("Migration marker not written: %s", err)
        _LOGGER.info(
            "Sync finished in %.1fs: %s",
            time.monotonic() - started,
            result.message,
        )
        return result

    def _run_plan(
        self, plan: SyncPlan, upsert_paths: list[str], removed_paths: list[str]
    ) -> SyncResult:
        if plan.removed and plan.total_files == 0:
            raise SyncError(
                "Refusing to delete remote files: the local scan found no files. "
                "Nothing on GitHub was changed."
            )
        if (
            self._config.sync_mode in SELECTION_MODES
            and not self._selections
            and plan.total_files == 0
        ):
            # The destructive half of this is the refusal above: no files
            # scanned, deletions pending. This is the other half. A selection
            # mode with nothing selected scans nothing, and the run used to
            # report "Sync completed. Upserted 0, deleted 0" - byte for byte
            # what a healthy sync with nothing to do looks like. Two such runs
            # went by unnoticed today while a broken selection was the reason,
            # and nothing in the product could tell them apart from success.
            label = (
                "Whitelist" if self._config.sync_mode == SYNC_MODE_WHITELIST else "Override"
            )
            raise SyncError(
                f"Refusing to sync: nothing is selected. {label} syncs only what "
                "you pick, so this run would change nothing. Select files in the "
                "tree, or switch to Blacklist."
            )
        self._progress_callback(
            {
                "status": "running",
                "current_action": "starting",
                "upsert_total": len(upsert_paths),
                "remove_total": len(removed_paths),
                "upsert_remaining": len(upsert_paths),
                "remove_remaining": len(removed_paths),
                "upsert_paths": upsert_paths[:50],
                "remove_paths": removed_paths[:50],
            }
        )
        if self._config.dry_run:
            return SyncResult(
                synced_count=len(plan.added) + len(plan.changed),
                deleted_count=len(plan.removed),
                skipped_count=len(plan.oversized),
                total_files=plan.total_files,
                message=(
                    "Dry run completed. "
                    f"Would upsert {len(plan.added) + len(plan.changed)} files "
                    f"and delete {len(plan.removed)} files."
                    + (
                        f" {len(plan.oversized)} too large for GitHub would be skipped."
                        if plan.oversized
                        else ""
                    )
                ),
            )

        skipped_count = len(plan.oversized)
        synced_count, skipped_mid_run, cancelled = self._commit_batch(upsert_paths, removed_paths)
        deleted_count = len(removed_paths) if not cancelled else 0
        skipped_count = len(plan.oversized) + skipped_mid_run
        if cancelled:
            return self._cancelled_result(plan, synced_count, deleted_count, skipped_count)

        too_large = (
            f" {len(plan.oversized)} too large for GitHub were skipped."
            if plan.oversized
            else ""
        )
        return SyncResult(
            synced_count=synced_count,
            deleted_count=deleted_count,
            skipped_count=skipped_count,
            total_files=plan.total_files,
            message=(
                "Sync completed. "
                f"Upserted {synced_count}, deleted {deleted_count}, skipped {skipped_count}."
                f"{too_large}"
            ),
        )

    def sensitive_files(self) -> list[str]:
        return list(self._sensitive_files)

    def restore_repo_skeleton(self) -> None:
        self._restore_repo_skeleton()

    def _cancelled_result(
        self, plan: SyncPlan, synced_count: int, deleted_count: int, skipped_count: int
    ) -> SyncResult:
        return SyncResult(
            synced_count=synced_count,
            deleted_count=deleted_count,
            skipped_count=skipped_count,
            total_files=plan.total_files,
            message=(
                "Sync cancelled. "
                f"Upserted {synced_count}, deleted {deleted_count}, skipped {skipped_count}."
            ),
            cancelled=True,
        )

    def _put_with_retry(self, relative: str, content: bytes, message: str | None = None, retries: int = 3) -> None:
        remote = self._github.get_content(relative)
        sha = remote.get("sha") if remote else None
        commit_message = message or f"sync: update {relative}"
        last_err: Exception | None = None
        for attempt in range(retries):
            try:
                self._github.put_content(
                    path=relative,
                    content=content,
                    message=commit_message,
                    sha=sha,
                )
                return
            except Exception as err:  # noqa: BLE001
                if not _is_sha_conflict(err) or attempt == retries - 1:
                    raise
                last_err = err
                time.sleep(0.5 * (attempt + 1))
                remote = self._github.get_content(relative)
                sha = remote.get("sha") if remote else None
        raise last_err  # type: ignore[misc]  # pragma: no cover

    def clean_remote_tree(self) -> None:
        """Empty the remote tree in one atomic commit (fast path); falls back to per-file deletes."""
        if self._cancel_requested():
            raise SyncError("Clean cancelled")
        try:
            self._reset_remote_tree(reset_history=False)
            return
        except SyncError:
            self._delete_remote_tree("")

    def nuke_remote_tree(self, reset_history: bool = True) -> None:
        """Reset the remote repository to an empty tree in a handful of API calls.

        With reset_history True an orphan commit replaces the whole history, so
        old commits, releases and tags are all dropped. Falls back to per-file
        deletes (with per-file progress and cancel) if the fast path fails.
        """
        if self._cancel_requested():
            raise SyncError("Nuke cancelled")
        try:
            self._reset_remote_tree(reset_history=reset_history)
            return
        except SyncError:
            self._delete_remote_tree("")

    def delete_all_releases_and_tags(self) -> None:
        releases = self._github.list_all_releases()
        for release in releases:
            release_id = release.get("id")
            tag_name = release.get("tag_name")
            if isinstance(release_id, int):
                try:
                    self._github.delete_release(release_id)
                except SyncError:
                    pass
            if isinstance(tag_name, str) and tag_name:
                try:
                    self._github.delete_tag(tag_name)
                except SyncError:
                    pass
        for tag_ref in self._github.list_tags():
            tag_name = tag_ref.get("name")
            if not isinstance(tag_name, str):
                ref = tag_ref.get("ref")
                if isinstance(ref, str):
                    tag_name = ref.rsplit("/", 1)[-1]
            if isinstance(tag_name, str) and tag_name:
                try:
                    self._github.delete_tag(tag_name)
                except SyncError:
                    pass

    def _reset_remote_tree(self, reset_history: bool) -> None:
        self._progress_callback(
            {
                "status": "running",
                "current_action": "resetting",
                "current_path": "",
                "upsert_total": 0,
                "remove_total": 0,
                "upsert_remaining": 0,
                "remove_remaining": 0,
                "upsert_paths": [],
                "remove_paths": [],
            }
        )
        parent_sha = None
        if not reset_history:
            parent_sha = self._github.get_branch_head_sha()
        empty_tree = self._github.create_git_tree(tree=[])
        tree_sha = empty_tree.get("sha")
        if not isinstance(tree_sha, str) or not tree_sha:
            raise SyncError("GitHub empty tree response was incomplete")
        commit = self._github.create_git_commit(
            message="sync: reset repository",
            tree_sha=tree_sha,
            parent_sha=parent_sha,
        )
        commit_sha = commit.get("sha")
        if not isinstance(commit_sha, str) or not commit_sha:
            raise SyncError("GitHub commit response was incomplete")
        self._github.update_branch_ref(commit_sha)

    def _delete_remote_tree(self, root: str) -> None:
        deletions = self._collect_remote_deletions(root)
        for index, item in enumerate(deletions):
            if self._cancel_requested():
                raise SyncError("Clean cancelled")
            item_path = item.get("path")
            if not isinstance(item_path, str):
                continue
            remote = self._github.get_content(item_path)
            sha = remote.get("sha") if remote else None
            if not isinstance(sha, str):
                continue
            self._github.delete_content(
                path=item_path,
                sha=sha,
                message=f"sync: delete {item_path}",
            )
            self._progress_callback(
                {
                    "status": "running",
                    "current_action": "resetting",
                    "current_path": item_path,
                    "upsert_total": 0,
                    "remove_total": len(deletions),
                    "upsert_remaining": 0,
                    "remove_remaining": len(deletions) - index - 1,
                    "upsert_paths": [],
                    "remove_paths": [str(d.get("path", "")) for d in deletions[:50]],
                }
            )

    def _collect_remote_deletions(self, root: str) -> list[dict[str, object]]:
        deletions: list[dict[str, object]] = []
        for item in self._github.list_directory_contents(root):
            item_type = item.get("type")
            item_path = item.get("path")
            if not isinstance(item_path, str):
                continue
            if item_type == "dir":
                deletions.extend(self._collect_remote_deletions(item_path))
                continue
            deletions.append({"path": item_path, "mode": "100644", "type": "blob", "sha": None})
        return deletions

    def _commit_batch(self, upsert_paths: list[str], removed_paths: list[str]) -> tuple[int, int, bool]:
        """Apply every upsert and delete as ONE commit.

        Per-file commits cost three API calls a file - get the SHA, put the
        content, write the commit - so a 224-file repository needed over 600
        calls, tripped the rate limiter, and left the repository half-updated
        if it failed partway. Staging blobs and writing one tree, one commit
        and one ref update makes it N+3, and the run is then atomic: either
        the whole change lands or none of it does.

        Blobs are content-addressed, so a retry of the tree/commit stage costs
        nothing - it reuses blobs GitHub already has.
        """
        entries: list[dict[str, object]] = []
        synced_count = 0
        skipped_count = 0
        total = len(upsert_paths)

        for index, relative in enumerate(upsert_paths):
            if self._cancel_requested():
                return synced_count, skipped_count, True
            self._progress_callback(
                {
                    "status": "running",
                    "current_action": "staging",
                    "current_path": relative,
                    "upsert_total": total,
                    "remove_total": len(removed_paths),
                    "upsert_remaining": total - index,
                    "remove_remaining": len(removed_paths),
                    "upsert_paths": upsert_paths[:50],
                    "remove_paths": removed_paths[:50],
                }
            )
            local_path = self._local_path_for(relative)
            if not local_path.exists():
                skipped_count += 1
                continue
            blob_sha = self._github.create_blob(local_path.read_bytes())
            entries.append(
                {
                    "path": relative,
                    # Preserve the exec bit; the per-file API used to lose it.
                    "mode": "100755" if local_path.stat().st_mode & 0o111 else "100644",
                    "type": "blob",
                    "sha": blob_sha,
                }
            )
            synced_count += 1

        for relative in removed_paths:
            # A null SHA is how the tree API is told to drop a path, so a
            # delete is staged in the same commit as everything else.
            entries.append({"path": relative, "mode": "100644", "type": "blob", "sha": None})

        if not entries:
            return synced_count, skipped_count, False

        self._progress_callback(
            {
                "status": "running",
                "current_action": "committing",
                "current_path": "",
                "upsert_total": total,
                "remove_total": len(removed_paths),
                "upsert_remaining": 0,
                "remove_remaining": 0,
                "upsert_paths": upsert_paths[:50],
                "remove_paths": removed_paths[:50],
            }
        )

        message = self._commit_message(synced_count, len(removed_paths))
        last_err: Exception | None = None
        for attempt in range(3):
            head_sha = self._github.get_branch_head_sha()
            base_tree = self._github.get_commit_tree_sha(head_sha)
            try:
                tree = self._github.create_git_tree(base_tree=base_tree, tree=entries)
                tree_sha = tree.get("sha")
                if not isinstance(tree_sha, str) or not tree_sha:
                    raise SyncError("GitHub tree response was incomplete")
                commit = self._github.create_git_commit(
                    message=message, tree_sha=tree_sha, parent_sha=head_sha
                )
                commit_sha = commit.get("sha")
                if not isinstance(commit_sha, str) or not commit_sha:
                    raise SyncError("GitHub commit response was incomplete")
                # force=False: if someone pushed while we were staging, that
                # push is not discarded - the retry rebuilds on top of it.
                self._github.update_branch_ref(commit_sha, force=False)
                return synced_count, skipped_count, False
            except SyncError as err:
                last_err = err
                if self._cancel_requested():
                    return synced_count, skipped_count, True
                if attempt == 2:
                    raise
                time.sleep(0.5 * (attempt + 1))
        raise last_err  # type: ignore[misc]  # pragma: no cover

    def _commit_message(self, synced_count: int, removed_count: int) -> str:
        parts = []
        if synced_count:
            parts.append(f"update {synced_count} file{'s' if synced_count != 1 else ''}")
        if removed_count:
            parts.append(f"remove {removed_count} file{'s' if removed_count != 1 else ''}")
        detail = ", ".join(parts) if parts else "no changes"
        return f"sync: {detail}"

    def _restore_repo_skeleton(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        skeleton_files = [
            ("README.md", repo_root / "README.md"),
            ("repository.yaml", repo_root / "repository.yaml"),
        ]
        for remote_path, local_path in skeleton_files:
            if self._cancel_requested():
                raise SyncError("Clean cancelled")
            if local_path.exists():
                self._put_with_retry(remote_path, local_path.read_bytes(), message=f"sync: restore {remote_path}")

    def _genuinely_gone(self, paths: list[str]) -> list[str]:
        """Keep only paths that are really gone, not merely out of scope.

        Narrowing a selection stops the scan seeing files it used to see, and
        the diff cannot tell that apart from a deletion. Treating it as one is
        how changing the selection removed files from a repository, so a path
        still sitting on disk is left where it is.
        """
        return [path for path in paths if not self._still_on_disk(path)]

    def _still_on_disk(self, relative: str) -> bool:
        try:
            return self._local_path_for(relative, roots=self._all_roots).exists()
        except (SyncError, OSError):
            # Cannot prove it is gone, so do not remove it.
            return True

    def _local_path_for(self, relative: str, roots: list[tuple[str, Path]] | None = None) -> Path:
        if self._config_prefix and relative.startswith(self._config_prefix + "/"):
            # Prefixed layout: the key carries config/, the filesystem does not.
            candidate = self._config_root / relative.removeprefix(self._config_prefix + "/")
        elif relative.startswith("media/"):
            candidate = Path("/media") / relative.removeprefix("media/")
        elif relative.startswith("share/"):
            candidate = Path("/share") / relative.removeprefix("share/")
        elif relative.startswith("ssl/"):
            candidate = Path("/ssl") / relative.removeprefix("ssl/")
        elif relative.startswith("backups/"):
            candidate = Path("/backup") / relative.removeprefix("backups/")
        elif relative.startswith("www/"):
            candidate = self._config_root / relative
        elif relative.startswith("addon_configs/"):
            candidate = self._addon_config_root / relative.removeprefix("addon_configs/")
        else:
            candidate = self._config_root / relative

        resolved = candidate.resolve()
        allowed_prefixes = tuple(
            root.resolve() for _, root in (roots or self._root_map) if root.exists()
        )
        if not any(resolved.is_relative_to(p) for p in allowed_prefixes):
            raise SyncError(f"Path escapes allowed sync roots: {relative}")
        return candidate

    def _is_config_root(self, name: str) -> bool:
        """Whether a root-map name refers to the config directory.

        The name is "" in flat layout and "config" in prefixed, and several
        checks care about which root rather than the literal string.
        """
        return name == self._config_prefix

    def _hash_roots(self, selection_mode: bool) -> list[tuple[str, Path]]:
        """Roots whose contents get hashed.

        _root_map keeps every root regardless of mode, because path resolution
        has to answer for a mount that is not being walked. This is the list
        that decides what actually gets uploaded.
        """
        if selection_mode:
            return self._walkable_roots()
        # Blacklist hashes the defaults plus anything the user has explicitly
        # enabled or selected - media, share, ssl and backups are opt-in.
        return [
            item
            for item in self._root_map
            if item[0] in BLACKLIST_DEFAULT_ROOTS
            or self._root_enabled(item[0])
            or self._mount_has_selection(item[0])
        ]

    def _root_enabled(self, name: str) -> bool:
        if self._is_config_root(name):
            return True
        if name == "addon_configs":
            return self._config.include_addon_configs
        if name == "media":
            return self._config.include_media
        if name == "share":
            return self._config.include_share
        if name == "ssl":
            return self._config.include_ssl
        if name == "backups":
            return self._config.include_backups
        if name == "www":
            return self._config.include_www
        return False

    def _build_selections(self) -> tuple[str, ...]:
        """Entries the sync may read from: picked paths, glob extras, mounts.

        ``safe_config_paths`` is folded in as a glob-based way to pick paths
        without browsing for them. Note the config root is never implied -
        whitelist with nothing selected must sync nothing.
        """
        entries: list[str] = [
            # Falsy entries are dropped before str(), or a None would become
            # the literal selection "None" - which matches nothing and looks
            # like a deliberate pick.
            str(entry)
            for entry in (getattr(self._config, "sync_paths", ()) or ())
            if entry
        ]
        entries.extend(str(e) for e in (getattr(self._config, "safe_config_paths", ()) or ()))
        entries.extend(name for name in MOUNT_KEYS if self._root_enabled(name))

        selections: list[str] = []
        seen: set[str] = set()
        for entry in entries:
            normalised = _normalise_selection(entry)
            if normalised is None:
                continue
            # Selections name local paths; index keys carry the root prefix.
            # Rewriting here means the rest of the engine - matching, the
            # .gitignore check, upserts, deletes - only ever deals in key
            # space, and layout stays a decision made in exactly one place.
            if self._config_prefix and _mount_prefix(normalised) == "":
                normalised = (
                    self._config_prefix
                    if normalised == WHOLE_CONFIG_ROOT
                    else f"{self._config_prefix}/{normalised}"
                )
            if normalised in seen:
                continue
            seen.add(normalised)
            selections.append(normalised)
        return tuple(selections)

    def _path_selected(self, key: str) -> bool:
        return any(_selection_matches(selection, key) for selection in self._selections)

    def _walkable_roots(self) -> list[tuple[str, Path]]:
        """Roots worth scanning for the current selection.

        Kept separate from ``_root_map``, which is what path resolution checks.
        The config root stays in the map either way, but is only walked when
        something selected lives inside it - otherwise a mount-only selection
        would hash the entire config tree and discard every digest.
        """
        return [item for item in self._root_map if self._root_needed(item[0])]

    def _root_needed(self, name: str) -> bool:
        """Whether a root has to be walked for the current selection."""
        if self._is_config_root(name):
            return any(_mount_prefix(str(sel)) == "" for sel in self._selections)
        return self._root_enabled(name) or self._mount_has_selection(name)

    def _mount_has_selection(self, name: str) -> bool:
        """True when a selected path is this mount or lives under it.

        Selecting the mount itself (``media``) or a subtree of it
        (``media/photos``) must both get ``/media`` walked. Matching only on
        the slash form left the tree's own whole-mount Select doing nothing,
        because the exact name never matched.
        """
        prefix = f"{name}/"
        return any(str(sel) == name or str(sel).startswith(prefix) for sel in self._selections)

    def _build_hash_index(self) -> dict[str, str]:
        mode = getattr(self._config, "sync_mode", SYNC_MODE_WHITELIST)
        selection_mode = mode in SELECTION_MODES
        override = mode == SYNC_MODE_OVERRIDE

        if selection_mode and not self._selections:
            # Nothing selected means nothing syncs. That holds in Override too:
            # "sync everything unfiltered" has to be a deliberate selection, not
            # the side effect of an empty list.
            self._sensitive_files = []
            self._oversized = []
            return {}

        # The warning list only covers paths the user actually picked, so it
        # reports what was blocked rather than every sensitive file on disk.
        self._sensitive_files = scan_sensitive_files(
            self._config_root,
            override=override,
            in_scope=self._path_selected if selection_mode else None,
        )
        ignore_matcher = GitIgnoreMatcher.from_file(self._config_root / ".gitignore")
        index: dict[str, str] = {}
        oversized: list[str] = []
        roots = self._hash_roots(selection_mode)
        for prefix, root in roots:
            if not root.exists():
                continue
            too_large: list[str] = []
            current = build_hash_index(root, override=override, oversized=too_large)
            for relative, digest in current.items():
                key = f"{prefix}/{relative}" if prefix else relative
                if selection_mode and not self._path_selected(key):
                    continue
                if ignore_matcher.has_rules and ignore_matcher.match(key):
                    continue
                index[key] = digest
            # Reported on the same terms as the index: a file that was out of
            # scope or ignored is not something the sync would have tried.
            for relative in too_large:
                key = f"{prefix}/{relative}" if prefix else relative
                if selection_mode and not self._path_selected(key):
                    continue
                if ignore_matcher.has_rules and ignore_matcher.match(key):
                    continue
                oversized.append(key)
        self._oversized = sorted(oversized)
        return index


def _is_sha_conflict(err: Exception) -> bool:
    message = str(err)
    return "HTTP 409" in message or "\"status\":\"409\"" in message or "\"status\": \"409\"" in message
