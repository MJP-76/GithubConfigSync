from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SyncConfig:
    repository: str
    branch: str
    token: str
    config_root: str
    dry_run: bool
    addon_config_root: str = "/addon_configs"
    include_media: bool = False
    include_share: bool = False
    include_ssl: bool = True
    include_backups: bool = False
    include_www: bool = True
    version_retention_count: int = 7


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
