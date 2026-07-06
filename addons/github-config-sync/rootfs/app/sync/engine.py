from __future__ import annotations

from pathlib import Path

from .github_client import GitHubClient
from .hashing import build_hash_index, diff_hash_indexes
from .models import SyncConfig, SyncPlan, SyncResult


class SyncEngine:
    def __init__(self, config: SyncConfig, previous_hash_index: dict[str, str]) -> None:
        self._config = config
        self._previous_hash_index = previous_hash_index
        self._config_root = Path(config.config_root)
        self._github = GitHubClient(
            repository=config.repository,
            branch=config.branch,
            token=config.token,
        )

    def probe_repository(self) -> tuple[bool, str]:
        return self._github.probe_repository()

    def plan(self) -> tuple[SyncPlan, dict[str, str]]:
        current_hash_index = build_hash_index(self._config_root)
        added, changed, removed = diff_hash_indexes(self._previous_hash_index, current_hash_index)
        plan = SyncPlan(
            added=added,
            changed=changed,
            removed=removed,
            total_files=len(current_hash_index),
        )
        return plan, current_hash_index

    def run(self, plan: SyncPlan) -> SyncResult:
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
        upsert_paths = [*plan.added, *plan.changed]

        for relative in upsert_paths:
            local_path = self._config_root / relative
            if not local_path.exists():
                skipped_count += 1
                continue
            remote = self._github.get_content(relative)
            sha = remote.get("sha") if remote else None
            self._github.put_content(
                path=relative,
                content=local_path.read_bytes(),
                message=f"sync: update {relative}",
                sha=sha,
            )
            synced_count += 1

        for relative in plan.removed:
            remote = self._github.get_content(relative)
            if not remote or "sha" not in remote:
                skipped_count += 1
                continue
            self._github.delete_content(
                path=relative,
                sha=remote["sha"],
                message=f"sync: delete {relative}",
            )
            deleted_count += 1

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
