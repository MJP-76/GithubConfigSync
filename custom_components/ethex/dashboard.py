"""Auto-create a Lovelace dashboard for the Ethex integration.

Home Assistant does not offer a public service/API for other integrations to
programmatically create a Lovelace *storage* dashboard - the collection that
backs Settings > Dashboards is only exposed as a local variable inside
`homeassistant.components.lovelace`'s own `async_setup`. To still offer a
one-click "create my dashboard" experience, this module:

1. Writes directly to the same on-disk storage Home Assistant's own
   onboarding flow uses to create its built-in "map" dashboard (see
   `homeassistant/components/lovelace/__init__.py::_create_map_dashboard`):
   a `lovelace_dashboards` index entry plus a `lovelace.<url_path>` config
   file. This makes the dashboard persist correctly across restarts and show
   up in Settings > Dashboards like any UI-created one.
2. Additionally registers the dashboard in the *current* running session
   (via `hass.data[LOVELACE_DATA]` and `frontend.async_register_built_in_panel`)
   so it appears in the sidebar immediately, without requiring a restart.

This pokes at lovelace/frontend internals that aren't a formally documented
integration API, so every public entry point here is defensive: failures are
logged and swallowed rather than allowed to break Ethex's own setup.
"""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store

from .dashboard_config import (
    DASHBOARD_ICON,
    DASHBOARD_TITLE,
    DASHBOARD_URL_PATH,
    build_dashboard_config,
)

_LOGGER = logging.getLogger(__name__)

_DASHBOARDS_STORAGE_KEY = "lovelace_dashboards"
_DASHBOARDS_STORAGE_VERSION = 1
_DASHBOARD_CONFIG_STORAGE_VERSION = 1


def _dashboard_item() -> dict:
    return {
        "id": DASHBOARD_URL_PATH,
        "url_path": DASHBOARD_URL_PATH,
        "title": DASHBOARD_TITLE,
        "icon": DASHBOARD_ICON,
        "show_in_sidebar": True,
        "require_admin": False,
        "mode": "storage",
    }


async def async_create_dashboard(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Create (or refresh) the Ethex dashboard. Never raises."""
    try:
        await _async_create_dashboard(hass, entry)
    except Exception:  # pylint: disable=broad-except
        _LOGGER.exception(
            "Failed to auto-create the Ethex dashboard; you can still add one "
            "manually via Settings > Dashboards"
        )


async def async_remove_dashboard(hass: HomeAssistant) -> None:
    """Remove the Ethex dashboard index entry and its config. Never raises."""
    try:
        await _async_remove_dashboard(hass)
    except Exception:  # pylint: disable=broad-except
        _LOGGER.exception("Failed to remove the Ethex dashboard")


async def _async_create_dashboard(hass: HomeAssistant, entry: ConfigEntry) -> None:
    dashboards_store: Store = Store(
        hass, _DASHBOARDS_STORAGE_VERSION, _DASHBOARDS_STORAGE_KEY
    )
    data = await dashboards_store.async_load() or {"items": []}
    items = data.setdefault("items", [])

    if not any(item.get("url_path") == DASHBOARD_URL_PATH for item in items):
        items.append(_dashboard_item())
        await dashboards_store.async_save(data)
        _LOGGER.debug("Added %s dashboard entry to storage", DASHBOARD_URL_PATH)

    view_config = _build_dashboard_config(hass, entry)

    config_store: Store = Store(
        hass, _DASHBOARD_CONFIG_STORAGE_VERSION, f"lovelace.{DASHBOARD_URL_PATH}"
    )
    await config_store.async_save({"config": view_config})

    await _async_register_live(hass, view_config)


async def _async_remove_dashboard(hass: HomeAssistant) -> None:
    dashboards_store: Store = Store(
        hass, _DASHBOARDS_STORAGE_VERSION, _DASHBOARDS_STORAGE_KEY
    )
    data = await dashboards_store.async_load()
    if data:
        items = data.get("items", [])
        remaining = [i for i in items if i.get("url_path") != DASHBOARD_URL_PATH]
        if len(remaining) != len(items):
            data["items"] = remaining
            await dashboards_store.async_save(data)

    config_store: Store = Store(
        hass, _DASHBOARD_CONFIG_STORAGE_VERSION, f"lovelace.{DASHBOARD_URL_PATH}"
    )
    await config_store.async_remove()

    try:
        from homeassistant.components import frontend
        from homeassistant.components.lovelace.const import LOVELACE_DATA

        frontend.async_remove_panel(hass, DASHBOARD_URL_PATH)
        lovelace_data = hass.data.get(LOVELACE_DATA)
        if lovelace_data is not None:
            lovelace_data.dashboards.pop(DASHBOARD_URL_PATH, None)
    except ImportError:
        pass


def _build_dashboard_config(hass: HomeAssistant, entry: ConfigEntry) -> dict:
    """Gather this entry's sensor entities and build the view config."""
    registry = er.async_get(hass)
    entity_ids = [
        e.entity_id
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.domain == "sensor"
    ]
    return build_dashboard_config(entity_ids)


async def _async_register_live(hass: HomeAssistant, view_config: dict) -> None:
    """Register the dashboard for the current session, without a restart."""
    try:
        from homeassistant.components import frontend
        from homeassistant.components.lovelace import dashboard as lovelace_dashboard
        from homeassistant.components.lovelace.const import LOVELACE_DATA
    except ImportError:
        _LOGGER.debug(
            "Lovelace/frontend not available; dashboard will appear after restart"
        )
        return

    lovelace_data = hass.data.get(LOVELACE_DATA)
    if lovelace_data is None:
        _LOGGER.debug("Lovelace not yet set up; dashboard will appear after restart")
        return

    storage_config = lovelace_dashboard.LovelaceStorage(hass, _dashboard_item())
    await storage_config.async_save(view_config)
    lovelace_data.dashboards[DASHBOARD_URL_PATH] = storage_config

    frontend.async_register_built_in_panel(
        hass,
        "lovelace",
        frontend_url_path=DASHBOARD_URL_PATH,
        require_admin=False,
        show_in_sidebar=True,
        sidebar_title=DASHBOARD_TITLE,
        sidebar_icon=DASHBOARD_ICON,
        config={"mode": "storage"},
        update=True,
    )
    _LOGGER.info("Ethex dashboard registered at /%s", DASHBOARD_URL_PATH)
