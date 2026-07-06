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
    CONF_GITHUB_TOKEN,
    CONF_IGNORE_PATTERNS,
    CONF_LOCAL_FOLDER,
    CONF_REPOSITORY,
    CONF_REMOTE_PATH,
    DEFAULT_BACKUP_INTERVAL_MINUTES,
    DOMAIN,
)
PLATFORMS = ("button", "sensor")


@dataclass
class BackupRuntimeData:
    client: GitHubBackupClient
    ignore_patterns: list[str]
    local_folder: Path
    remote_path: str
    last_sync: str | None = None
    last_commit_url: str | None = None
    last_error: str | None = None
    last_status: str | None = None
    unsubscribe: Callable[[], None] | None = None


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    token = entry.data[CONF_GITHUB_TOKEN]
    repository = entry.data[CONF_REPOSITORY]
    local_folder = Path(entry.data[CONF_LOCAL_FOLDER])
    remote_path = entry.data.get(CONF_REMOTE_PATH, ".")
    ignore_patterns = entry.data.get(CONF_IGNORE_PATTERNS, [])
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
        local_folder=local_folder,
        remote_path=remote_path,
    )
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime

    if interval_minutes and interval_minutes > 0:

        async def _periodic_sync(_now) -> None:
            await async_request_sync(hass, entry.entry_id, "scheduled")

        runtime.unsubscribe = async_track_time_interval(
            hass, _periodic_sync, timedelta(minutes=interval_minutes)
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


async def async_request_sync(
    hass: HomeAssistant, entry_id: str, trigger: str = "manual"
) -> tuple[bool, str | None]:
    runtime: BackupRuntimeData = hass.data[DOMAIN][entry_id]
    local_folder = runtime.local_folder
    ignore_patterns = runtime.ignore_patterns
    remote_path = runtime.remote_path

    runtime.last_status = "running"
    runtime.last_error = None
    runtime.last_commit_url = None

    try:
        result = await runtime.client.async_sync_local_folder_to_github(
            local_folder=local_folder,
            remote_path=remote_path,
            ignore_patterns=ignore_patterns,
            message=f"{trigger} folder sync",
        )
        runtime.last_commit_url = (
            result.get("last_result", {}).get("content", {}).get("html_url")
        )
        runtime.last_status = "ok"
        runtime.last_sync = f"{result.get('synced', 0)} files"
        return True, runtime.last_commit_url
    except GitHubError as err:
        runtime.last_status = "error"
        runtime.last_error = str(err)
        return False, None
