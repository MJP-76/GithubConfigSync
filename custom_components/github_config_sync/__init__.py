from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.event import async_track_time_interval

from .client import GitHubBackupClient, GitHubError
from .const import (
    CONF_BACKUP_INTERVAL_MINUTES,
    CONF_BACKUP_PREFIX,
    CONF_GITHUB_TOKEN,
    CONF_IGNORE_PATTERNS,
    CONF_REPOSITORY,
    DEFAULT_BACKUP_INTERVAL_MINUTES,
    DOMAIN,
)
PLATFORMS = ("button", "sensor")


@dataclass
class BackupRuntimeData:
    client: GitHubBackupClient
    ignore_patterns: list[str]
    backup_prefix: str
    config_dir: Path
    last_backup: str | None = None
    last_commit_url: str | None = None
    last_error: str | None = None
    last_status: str | None = None
    unsubscribe: Callable[[], None] | None = None


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    token = entry.data[CONF_GITHUB_TOKEN]
    repository = entry.data[CONF_REPOSITORY]
    ignore_patterns = entry.data.get(CONF_IGNORE_PATTERNS, [])
    backup_prefix = entry.data.get(CONF_BACKUP_PREFIX, "home-assistant-config")
    interval_minutes = entry.data.get(
        CONF_BACKUP_INTERVAL_MINUTES, DEFAULT_BACKUP_INTERVAL_MINUTES
    )

    client = GitHubBackupClient(hass, token=token, repository=repository)
    try:
        await client.async_validate()
    except GitHubError as err:
        raise ConfigEntryNotReady(str(err)) from err

    runtime = BackupRuntimeData(
        client=client,
        ignore_patterns=ignore_patterns,
        backup_prefix=backup_prefix,
        config_dir=Path(hass.config.config_dir),
    )
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime

    if interval_minutes and interval_minutes > 0:

        async def _periodic_backup(_now) -> None:
            await async_request_backup(hass, entry.entry_id, "scheduled")

        runtime.unsubscribe = async_track_time_interval(
            hass, _periodic_backup, timedelta(minutes=interval_minutes)
        )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        runtime: BackupRuntimeData = hass.data[DOMAIN].pop(entry.entry_id)
        if runtime.unsubscribe:
            runtime.unsubscribe()
    return unload_ok


async def async_request_backup(
    hass: HomeAssistant, entry_id: str, trigger: str = "manual"
) -> tuple[bool, str | None]:
    runtime: BackupRuntimeData = hass.data[DOMAIN][entry_id]
    config_dir = runtime.config_dir
    ignore_patterns = runtime.ignore_patterns
    backup_prefix = runtime.backup_prefix

    runtime.last_status = "running"
    runtime.last_error = None

    try:
        archive_name, archive_bytes = await runtime.client.async_build_archive(
            config_dir,
            backup_prefix=backup_prefix,
            ignore_patterns=ignore_patterns,
        )
        result = await runtime.client.async_upload_archive(
            archive_name=archive_name,
            archive_bytes=archive_bytes,
            message=f"{trigger} backup {archive_name}",
        )
        runtime.last_status = "ok"
        runtime.last_backup = archive_name
        runtime.last_commit_url = result.get("html_url")
        return True, runtime.last_commit_url
    except GitHubError as err:
        runtime.last_status = "error"
        runtime.last_error = str(err)
        return False, None
