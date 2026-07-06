from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.event import async_call_later, async_track_time_interval

from .client import GitHubBackupClient, GitHubError
from .const import (
    CONF_BACKUP_INTERVAL_MINUTES,
    CONF_BACKUP_INTERVAL_HOURS,
    CONF_EXTRA_IGNORE_PATTERNS,
    CONF_GITHUB_TOKEN,
    CONF_IGNORE_PATTERNS,
    CONF_REPOSITORY,
    CONF_SYNC_START_TIME,
    DEFAULT_BACKUP_INTERVAL_MINUTES,
    DOMAIN,
)
PLATFORMS = ("button", "sensor")


@dataclass
class BackupRuntimeData:
    client: GitHubBackupClient
    ignore_patterns: list[str]
    extra_ignore_patterns: list[str]
    interval_hours: int
    sync_start_time: str
    last_sync: str | None = None
    last_commit_url: str | None = None
    last_error: str | None = None
    last_status: str | None = None
    unsubscribe: Callable[[], None] | None = None


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    token = entry.data[CONF_GITHUB_TOKEN]
    repository = entry.data[CONF_REPOSITORY]
    ignore_patterns = entry.data.get(CONF_IGNORE_PATTERNS, [])
    extra_ignore_patterns = entry.data.get(CONF_EXTRA_IGNORE_PATTERNS, [])
    interval_hours = entry.data.get(CONF_BACKUP_INTERVAL_HOURS, 24)
    sync_start_time = entry.data.get(CONF_SYNC_START_TIME, "03:00")

    client = GitHubBackupClient(hass, token=token, repository=repository)
    try:
        await client.async_validate()
    except GitHubError as err:
        raise ConfigEntryNotReady(str(err)) from err

    runtime = BackupRuntimeData(
        client=client,
        ignore_patterns=ignore_patterns,
        extra_ignore_patterns=extra_ignore_patterns,
        interval_hours=interval_hours,
        sync_start_time=sync_start_time,
    )
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime

    runtime.unsubscribe = _schedule_next_sync(hass, entry.entry_id)

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
    local_folder = Path(hass.config.config_dir)
    ignore_patterns = runtime.ignore_patterns
    extra_ignore_patterns = runtime.extra_ignore_patterns
    remote_path = "."

    runtime.last_status = "running"
    runtime.last_error = None
    runtime.last_commit_url = None

    try:
        await runtime.client.async_write_gitignore(
            local_folder=local_folder,
            extra_patterns=extra_ignore_patterns,
        )
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


def _schedule_next_sync(hass: HomeAssistant, entry_id: str):
    runtime: BackupRuntimeData = hass.data[DOMAIN][entry_id]
    hour, minute = (int(part) for part in runtime.sync_start_time.split(":"))
    now = datetime.now(timezone.utc).astimezone()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target = target + timedelta(hours=runtime.interval_hours)

    delay = (target - now).total_seconds()

    async def _run_now(_now):
        await async_request_sync(hass, entry_id, "scheduled")

    def _reschedule(_now):
        unsub = async_track_time_interval(
            hass, _run_now, timedelta(hours=runtime.interval_hours)
        )
        runtime.unsubscribe = unsub

    return async_call_later(hass, delay, _reschedule)
