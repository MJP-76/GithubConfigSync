from __future__ import annotations

from pathlib import Path
import datetime as dt
from typing import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

from .github_client import GitHubClient
from .hashing import build_hash_index, diff_hash_indexes, is_ignored
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
            ("backups", Path("/backups")),
            ("www", Path("/www")),
        ]
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

        if self._config.version_retention_count > 0:
            self._sync_version_snapshot()
            self._rotate_version_snapshots()

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

    def clean_remote_tree(self) -> None:
        self._delete_remote_tree("")

    def restore_repo_skeleton(self) -> None:
        self._restore_repo_skeleton()

    def _sync_version_snapshot(self) -> None:
        timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        version_root = f"versions/{timestamp}"
        for prefix, root in self._root_map:
            if not root.exists():
                continue
            for path in sorted(root.rglob("*")):
                if not path.is_file():
                    continue
                relative = path.relative_to(root).as_posix()
                if is_ignored(relative):
                    continue
                target = f"{version_root}/{prefix}/{relative}" if prefix else f"{version_root}/{relative}"
                self._put_with_retry(target, path.read_bytes(), message=f"sync: snapshot {target}")

    def _rotate_version_snapshots(self) -> None:
        keep = max(1, self._config.version_retention_count)
        version_dirs = [
            item.get("name")
            for item in self._github.list_directory_contents("versions")
            if item.get("type") == "dir" and isinstance(item.get("name"), str)
        ]
        if len(version_dirs) <= keep:
            return
        for version in sorted(version_dirs)[: len(version_dirs) - keep]:
            self._delete_remote_tree(f"versions/{version}")

    def prune_versions_older_than_days(self, days: int) -> None:
        if days < 1:
            return
        cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
        version_dirs = [
            item
            for item in self._github.list_directory_contents("versions")
            if item.get("type") == "dir" and isinstance(item.get("name"), str)
        ]
        for item in version_dirs:
            name = item["name"]
            try:
                parsed = dt.datetime.strptime(name, "%Y%m%dT%H%M%SZ").replace(tzinfo=dt.timezone.utc)
            except ValueError:
                continue
            if parsed < cutoff:
                self._delete_remote_tree(f"versions/{name}")

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

    def _put_with_retry(self, relative: str, content: bytes, message: str | None = None) -> None:
        remote = self._github.get_content(relative)
        sha = remote.get("sha") if remote else None
        commit_message = message or f"sync: update {relative}"
        try:
            self._github.put_content(
                path=relative,
                content=content,
                message=commit_message,
                sha=sha,
            )
        except Exception as err:  # noqa: BLE001
            if not _is_sha_conflict(err):
                raise
            remote = self._github.get_content(relative)
            sha = remote.get("sha") if remote else None
            self._github.put_content(
                path=relative,
                content=content,
                message=commit_message,
                sha=sha,
            )

    def _delete_remote_tree(self, root: str) -> None:
        for item in self._github.list_directory_contents(root):
            item_type = item.get("type")
            item_path = item.get("path")
            if not isinstance(item_path, str):
                continue
            if item_type == "dir":
                self._delete_remote_tree(item_path)
                continue
            sha = item.get("sha")
            if not isinstance(sha, str):
                continue
            self._github.delete_content(
                path=item_path,
                sha=sha,
                message=f"sync: delete {item_path}",
            )

    def _delete_remote_tree_except(self, root: str, excluded_names: set[str]) -> None:
        for item in self._github.list_directory_contents(root):
            item_type = item.get("type")
            item_name = item.get("name")
            item_path = item.get("path")
            if not isinstance(item_name, str) or not isinstance(item_path, str):
                continue
            if root == "" and item_name in excluded_names:
                continue
            if item_type == "dir":
                self._delete_remote_tree_except(item_path, excluded_names)
                continue
            sha = item.get("sha")
            if not isinstance(sha, str):
                continue
            self._github.delete_content(
                path=item_path,
                sha=sha,
                message=f"sync: delete {item_path}",
            )

    def _apply_upserts(self, upsert_paths: list[str], removed_paths: list[str]) -> tuple[int, int, bool]:
        if not upsert_paths:
            return 0, 0, False
        synced_count = 0
        skipped_count = 0
        cancelled = False
        with ThreadPoolExecutor(max_workers=min(4, len(upsert_paths))) as executor:
            futures = {}
            for relative in upsert_paths:
                if self._cancel_requested():
                    cancelled = True
                    break
                self._progress_callback(
                    {
                        "status": "running",
                        "current_action": "upserting",
                        "current_path": relative,
                        "upsert_total": len(upsert_paths),
                        "remove_total": len(removed_paths),
                        "upsert_remaining": len(upsert_paths),
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
            for future in as_completed(futures):
                future.result()
                synced_count += 1
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
            for relative in removed_paths:
                if self._cancel_requested():
                    cancelled = True
                    break
                self._progress_callback(
                    {
                        "status": "running",
                        "current_action": "deleting",
                        "current_path": relative,
                        "upsert_total": len(upsert_paths),
                        "remove_total": len(removed_paths),
                        "upsert_remaining": 0,
                        "remove_remaining": len(removed_paths),
                        "upsert_paths": [],
                        "remove_paths": removed_paths[:50],
                    }
                )
                futures[executor.submit(self._delete_one, relative)] = relative
            for future in as_completed(futures):
                did_delete = future.result()
                if did_delete:
                    deleted_count += 1
                else:
                    skipped_count += 1
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
            if local_path.exists():
                self._put_with_retry(remote_path, local_path.read_bytes(), message=f"sync: restore {remote_path}")

    def _build_hash_index(self) -> dict[str, str]:
        index: dict[str, str] = {}
        for prefix, root in self._root_map:
            if not root.exists():
                continue
            current = build_hash_index(root)
            for relative, digest in current.items():
                key = f"{prefix}/{relative}" if prefix else relative
                index[key] = digest
        return index

    def _local_path_for(self, relative: str) -> Path:
        if relative.startswith("media/"):
            return Path("/media") / relative.removeprefix("media/")
        if relative.startswith("share/"):
            return Path("/share") / relative.removeprefix("share/")
        if relative.startswith("ssl/"):
            return Path("/ssl") / relative.removeprefix("ssl/")
        if relative.startswith("backups/"):
            return Path("/backups") / relative.removeprefix("backups/")
        if relative.startswith("www/"):
            return Path("/www") / relative.removeprefix("www/")
        if relative.startswith("addon_configs/"):
            return self._addon_config_root / relative.removeprefix("addon_configs/")
        return self._config_root / relative

    def _root_enabled(self, name: str) -> bool:
        if name == "":
            return True
        if name == "addon_configs":
            return True
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
