from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import async_request_sync


class GitHubSyncButton(ButtonEntity):
    _attr_has_entity_name = True
    _attr_name = "Sync folder now"
    _attr_icon = "mdi:github"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_sync_now"

    async def async_press(self) -> None:
        await async_request_sync(self.hass, self.entry.entry_id, "manual")

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([GitHubSyncButton(hass, entry)])
