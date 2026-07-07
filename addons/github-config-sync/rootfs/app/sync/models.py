from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SyncConfig:
    repository: str
    branch: str
    token: str
    config_root: str
    dry_run: bool


@dataclass(frozen=True)
class SyncPlan:
    added: list[str]
    changed: list[str]
    removed: list[str]
    total_files: int


@dataclass(frozen=True)
class SyncResult:
    synced_count: int
    deleted_count: int
    skipped_count: int
    total_files: int
    message: str
    cancelled: bool = False
