from __future__ import annotations

from dataclasses import dataclass, field

REPO_LAYOUT_FLAT = "flat"
REPO_LAYOUT_PREFIXED = "prefixed"
REPO_LAYOUTS = (REPO_LAYOUT_FLAT, REPO_LAYOUT_PREFIXED)


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
    include_ssl: bool = False
    include_backups: bool = False
    include_www: bool = False
    include_addon_configs: bool = False
    sync_mode: str = "whitelist"
    security_override_all_filters: bool = False
    safe_config_paths: tuple[str, ...] = ()
    sync_paths: tuple[str, ...] = ()
    # "flat": config files sit at the repository root (pre-1.7.2 behaviour).
    # "prefixed": config files live under config/ and each mount keeps its own
    # name, so nothing in the repository shares a namespace with the add-on's
    # own files or with anything else the user keeps there.
    repo_layout: str = REPO_LAYOUT_PREFIXED


@dataclass(frozen=True)
class SyncPlan:
    added: list[str]
    changed: list[str]
    removed: list[str]
    total_files: int
    # In scope, but too large for GitHub to accept. Skipped with a report
    # rather than attempted, so one oversized file cannot fail the run.
    oversized: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SyncResult:
    synced_count: int
    deleted_count: int
    skipped_count: int
    total_files: int
    message: str
    cancelled: bool = False
