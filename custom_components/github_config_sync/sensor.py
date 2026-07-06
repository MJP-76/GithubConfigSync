from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN


class GitHubSyncSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Folder sync status"
    _attr_icon = "mdi:cloud-sync"
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_sync_status"

    @property
    def native_value(self):
        runtime = self.hass.data[DOMAIN][self.entry.entry_id]
        return runtime.last_status or "idle"

    @property
    def extra_state_attributes(self):
        runtime = self.hass.data[DOMAIN][self.entry.entry_id]
        return {
            "last_sync": runtime.last_sync,
            "last_commit_url": runtime.last_commit_url,
            "last_error": runtime.last_error,
        }

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([GitHubSyncSensor(hass, entry)])
