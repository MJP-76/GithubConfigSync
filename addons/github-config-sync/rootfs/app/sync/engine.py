from __future__ import annotations

from pathlib import Path
from typing import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

from .errors import SyncError
from .github_client import GitHubClient
from .hashing import GitIgnoreMatcher, build_hash_index, diff_hash_indexes, scan_sensitive_files
from .models import SyncConfig, SyncPlan, SyncResult


class SyncEngine:
    def __init__(self, config: SyncConfig, previous_hash_index: dict[str, str]) -> None:
        self._config = config
        self._previous_hash_index = previous_hash_index
        self._config_root = Path(config.config_root)
        addon_config_root = getattr(config, "addon_config_root", "/addon_configs")
        self._addon_config_root = Path(addon_config_root) if addon_config_root else Path("/__missing_addon_configs__")
        self._root_map = [
            ("", self._config_root),
            ("addon_configs", self._addon_config_root),
            ("media", Path("/media")),
            ("share", Path("/share")),
            ("ssl", Path("/ssl")),
            ("backups", Path("/backup")),
            ("www", self._config_root / "www"),
        ]
        if self._config.sync_mode == "whitelist":
            self._root_map = [
                item
                for item in self._root_map
                if self._root_enabled(item[0])
            ]
        self._github = GitHubClient(
            repository=config.repository,
            branch=config.branch,
            token=config.token,
        )
        self._sensitive_files: list[str] = []
        self._cancel_requested: Callable[[], bool] = lambda: False
        self._progress_callback: Callable[[dict[str, object]], None] = lambda _payload: None

    def set_cancel_checker(self, cancel_requested: Callable[[], bool]) -> None:
        self._cancel_requested = cancel_requested

    def set_progress_callback(self, progress_callback: Callable[[dict[str, object]], None]) -> None:
        self._progress_callback = progress_callback

    def probe_repository(self) -> tuple[bool, str]:
        return self._github.probe_repository()

    def plan(self) -> tuple[SyncPlan, dict[str, str]]:
        current_hash_index = self._build_hash_index()
        added, changed, removed = diff_hash_indexes(self._previous_hash_index, current_hash_index)
        plan = SyncPlan(
            added=added,
            changed=changed,
            removed=removed,
            total_files=len(current_hash_index),
        )
        return plan, current_hash_index

    def clean_plan(self) -> tuple[SyncPlan, dict[str, str]]:
        current_hash_index = self._build_hash_index()
        all_paths = sorted(current_hash_index.keys())
        removed_paths = sorted(path for path in self._previous_hash_index.keys() if path not in current_hash_index)
        plan = SyncPlan(
            added=all_paths,
            changed=[],
            removed=removed_paths,
            total_files=len(current_hash_index),
        )
        return plan, current_hash_index

    def run(self, plan: SyncPlan) -> SyncResult:
        if plan.removed and plan.total_files == 0:
            raise SyncError(
                "Refusing to delete remote files: the local scan found no files. "
                "Nothing on GitHub was changed."
            )
        upsert_paths = [*plan.added, *plan.changed]
        removed_paths = list(plan.removed)
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
                skipped_count=0,
                total_files=plan.total_files,
                message=(
                    "Dry run completed. "
                    f"Would upsert {len(plan.added) + len(plan.changed)} files "
                    f"and delete {len(plan.removed)} files."
                ),
            )

        synced_count = 0
        deleted_count = 0
        skipped_count = 0
        synced_count, skipped_upserts, cancelled = self._apply_upserts(upsert_paths, removed_paths)
        if cancelled:
            return self._cancelled_result(plan, synced_count, deleted_count, skipped_count + skipped_upserts)
        deleted_count, skipped_deletes, cancelled = self._apply_deletes(upsert_paths, removed_paths)
        if cancelled:
            return self._cancelled_result(plan, synced_count, deleted_count, skipped_count + skipped_upserts + skipped_deletes)
        skipped_count = skipped_upserts + skipped_deletes

        return SyncResult(
            synced_count=synced_count,
            deleted_count=deleted_count,
            skipped_count=skipped_count,
            total_files=plan.total_files,
            message=(
                "Sync completed. "
                f"Upserted {synced_count}, deleted {deleted_count}, skipped {skipped_count}."
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
        import time
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

    def _apply_upserts(self, upsert_paths: list[str], removed_paths: list[str]) -> tuple[int, int, bool]:
        if not upsert_paths:
            return 0, 0, False
        synced_count = 0
        skipped_count = 0
        cancelled = False
        with ThreadPoolExecutor(max_workers=min(4, len(upsert_paths))) as executor:
            futures = {}
            total = len(upsert_paths)
            for index, relative in enumerate(upsert_paths):
                if self._cancel_requested():
                    cancelled = True
                    break
                remaining = total - index
                self._progress_callback(
                    {
                        "status": "running",
                        "current_action": "upserting",
                        "current_path": relative,
                        "upsert_total": total,
                        "remove_total": len(removed_paths),
                        "upsert_remaining": remaining,
                        "remove_remaining": len(removed_paths),
                        "upsert_paths": upsert_paths[:50],
                        "remove_paths": removed_paths[:50],
                    }
                )
                local_path = self._local_path_for(relative)
                if not local_path.exists():
                    skipped_count += 1
                    continue
                futures[executor.submit(self._put_with_retry, relative, local_path.read_bytes())] = relative
            self._progress_callback(
                {
                    "status": "running",
                    "current_action": "upserting",
                    "current_path": "",
                    "upsert_total": total,
                    "remove_total": len(removed_paths),
                    "upsert_remaining": len(futures),
                    "remove_remaining": len(removed_paths),
                    "upsert_paths": upsert_paths[:50],
                    "remove_paths": removed_paths[:50],
                }
            )
            for future in as_completed(futures):
                future.result()
                synced_count += 1
                self._progress_callback(
                    {
                        "status": "running",
                        "current_action": "upserting",
                        "current_path": "",
                        "upsert_total": total,
                        "remove_total": len(removed_paths),
                        "upsert_remaining": len(futures) - synced_count,
                        "remove_remaining": len(removed_paths),
                        "upsert_paths": upsert_paths[:50],
                        "remove_paths": removed_paths[:50],
                    }
                )
        if self._cancel_requested():
            cancelled = True
        return synced_count, skipped_count, cancelled

    def _apply_deletes(self, upsert_paths: list[str], removed_paths: list[str]) -> tuple[int, int, bool]:
        if not removed_paths:
            return 0, 0, False
        deleted_count = 0
        skipped_count = 0
        cancelled = False
        with ThreadPoolExecutor(max_workers=min(4, len(removed_paths))) as executor:
            futures = {}
            total = len(removed_paths)
            for index, relative in enumerate(removed_paths):
                if self._cancel_requested():
                    cancelled = True
                    break
                remaining = total - index
                self._progress_callback(
                    {
                        "status": "running",
                        "current_action": "deleting",
                        "current_path": relative,
                        "upsert_total": len(upsert_paths),
                        "remove_total": total,
                        "upsert_remaining": 0,
                        "remove_remaining": remaining,
                        "upsert_paths": [],
                        "remove_paths": removed_paths[:50],
                    }
                )
                futures[executor.submit(self._delete_one, relative)] = relative
            self._progress_callback(
                {
                    "status": "running",
                    "current_action": "deleting",
                    "current_path": "",
                    "upsert_total": len(upsert_paths),
                    "remove_total": total,
                    "upsert_remaining": 0,
                    "remove_remaining": len(futures),
                    "upsert_paths": [],
                    "remove_paths": removed_paths[:50],
                }
            )
            for future in as_completed(futures):
                did_delete = future.result()
                if did_delete:
                    deleted_count += 1
                else:
                    skipped_count += 1
                self._progress_callback(
                    {
                        "status": "running",
                        "current_action": "deleting",
                        "current_path": "",
                        "upsert_total": len(upsert_paths),
                        "remove_total": total,
                        "upsert_remaining": 0,
                        "remove_remaining": len(futures) - deleted_count - skipped_count,
                        "upsert_paths": [],
                        "remove_paths": removed_paths[:50],
                    }
                )
        if self._cancel_requested():
            cancelled = True
        return deleted_count, skipped_count, cancelled

    def _delete_one(self, relative: str) -> bool:
        remote = self._github.get_content(relative)
        if not remote or "sha" not in remote:
            return False
        self._github.delete_content(
            path=relative,
            sha=remote["sha"],
            message=f"sync: delete {relative}",
        )
        return True

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

    def _build_hash_index(self) -> dict[str, str]:
        self._sensitive_files = scan_sensitive_files(self._config_root)
        ignore_matcher = GitIgnoreMatcher.from_file(self._config_root / ".gitignore")
        index: dict[str, str] = {}
        for prefix, root in self._root_map:
            if not root.exists():
                continue
            current = build_hash_index(root)
            for relative, digest in current.items():
                key = f"{prefix}/{relative}" if prefix else relative
                if ignore_matcher.has_rules and ignore_matcher.match(key):
                    continue
                index[key] = digest
        return index

    def _local_path_for(self, relative: str) -> Path:
        if relative.startswith("media/"):
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
            root.resolve() for _, root in self._root_map if root.exists()
        )
        if not any(resolved.is_relative_to(p) for p in allowed_prefixes):
            raise SyncError(f"Path escapes allowed sync roots: {relative}")
        return candidate

    def _root_enabled(self, name: str) -> bool:
        if name == "":
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


def _is_sha_conflict(err: Exception) -> bool:
    message = str(err)
    return "HTTP 409" in message or "\"status\":\"409\"" in message or "\"status\": \"409\"" in message
