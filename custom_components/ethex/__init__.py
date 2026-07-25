"""The Ethex integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import EthexClient
from .const import CONF_CREATE_DASHBOARD, CONF_PASSWORD, CONF_USERNAME, DEFAULT_CREATE_DASHBOARD, DOMAIN
from .coordinator import EthexCoordinator
from .dashboard import async_create_dashboard, async_remove_dashboard

PLATFORMS = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Ethex from a config entry."""
    session = async_create_clientsession(hass)
    client = EthexClient(session, entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD])

    coordinator = EthexCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    if _wants_dashboard(entry):
        # Entities are registered synchronously during platform setup above,
        # so the entity registry is already populated for this entry here.
        await async_create_dashboard(hass, entry)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


def _wants_dashboard(entry: ConfigEntry) -> bool:
    return entry.options.get(
        CONF_CREATE_DASHBOARD,
        entry.data.get(CONF_CREATE_DASHBOARD, DEFAULT_CREATE_DASHBOARD),
    )


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options updates (e.g. the dashboard toggle)."""
    if _wants_dashboard(entry):
        await async_create_dashboard(hass, entry)
    else:
        await async_remove_dashboard(hass)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok

