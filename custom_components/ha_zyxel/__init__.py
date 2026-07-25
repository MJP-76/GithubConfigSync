"""The Zyxel integration."""
import asyncio
import logging
from collections.abc import Mapping
from datetime import timedelta

import async_timeout
from homeassistant.components import frontend
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from custom_components.ha_zyxel.backend import EX3301T0Client, NWA50AXClient, normalize_zysh_status
from custom_components.ha_zyxel.const import (
    CONF_DEVICE_TYPE,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_USERNAME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

from nr7101 import nr7101

PLATFORMS = ["sensor", "button"]
ZyXEL_DASHBOARD_ID = "zyxel-devices"
ZyXEL_DASHBOARD_STORAGE_KEY = f"lovelace.{ZyXEL_DASHBOARD_ID}"
ZyXEL_DASHBOARDS_STORAGE_KEY = "lovelace_dashboards"
ZyXEL_DASHBOARD_URL_PATH = "zyxel-devices"
ZYXEL_ENTITY_PREFIXES = ("sensor.", "button.")
ZYXEL_DASHBOARD_REFRESH_LISTENER = "_zyxel_dashboard_refresh_listener"
ZYXEL_HA_STARTED_LISTENER = "_zyxel_ha_started_listener"


_DASHBOARD_LOGO_URL = (
    "https://raw.githubusercontent.com/MJP-76/ha-zyxel/main/resources/logo.png"
)


def _zyxel_dashboard_config(hass: HomeAssistant, device_cards: list[dict[str, object]]) -> dict:
    # Sections in a 'sections'-type view must NOT have a 'type' key — they are
    # plain section objects with optional 'title', 'column_span', and 'cards'.
    header_section: dict[str, object] = {
        "title": "Zyxel Devices",
        "column_span": 4,
        "cards": [
            {
                "type": "picture",
                "image": _DASHBOARD_LOGO_URL,
                "alt_text": "Zyxel",
                "style": "height:60px;object-fit:contain;background:transparent",
            },
            {
                "type": "heading",
                "heading": "Zyxel Devices",
                "heading_style": "title",
                "icon": "mdi:router",
            },
        ],
    }
    empty_section: dict[str, object] = {
        "title": "No devices",
        "cards": [
            {
                "type": "markdown",
                "content": "No Zyxel integrations are currently configured.\n\nGo to **Settings → Devices & Services** to add a device.",
            }
        ],
    }
    overview_cards = device_cards if device_cards else [empty_section]
    sections = [header_section, *overview_cards]
    views = [
        {
            "title": "Overview",
            "path": ZyXEL_DASHBOARD_URL_PATH,
            "icon": "mdi:router",
            "theme": "Backend-selected",
            "type": "sections",
            "sections": sections,
        }
    ]
    for section in _device_detail_sections(hass):
        heading = section.get("title", "Device")
        views.append(
            {
                "title": heading,
                "path": heading.lower().replace(" ", "-").replace("(", "").replace(")", "").replace(".", "-"),
                "icon": "mdi:access-point",
                "theme": "Backend-selected",
                "type": "sections",
                "sections": [section],
            }
        )
    return {
        "config": {
            "title": "Zyxel Devices",
            "views": views,
        }
    }

def _device_title(entry) -> str:
    if entry is None:
        return "Zyxel Device"
    if entry.name_by_user:
        return entry.name_by_user
    if entry.name:
        return entry.name
    return "Zyxel Device"


def _device_summary_entities(hass: HomeAssistant, device_id: str) -> list[str]:
    entity_registry = er.async_get(hass)
    summary_order = [
        "host_name",
        "ModelName",
        "firmware_version",
        "Internet",
        "Ethernet",
        "IP_Address",
        "Nebula_Cloud_status",
        "serial_number",
        "mode",
    ]
    entities: list[str] = []
    for leaf in summary_order:
        for entity in entity_registry.entities.values():
            if entity.platform != DOMAIN or entity.device_id != device_id:
                continue
            if entity.disabled_by is not None:
                continue
            if leaf.lower() in entity.entity_id.lower() or leaf.lower() in entity.original_name.lower():
                entities.append(entity.entity_id)
                break
    return entities


def _entry_host(entry: ConfigEntry) -> str:
    host = entry.data.get(CONF_HOST, "")
    if host.startswith(("http://", "https://")):
        host = host.split("://", 1)[1]
    return host.split("/", 1)[0]


def _hostish_title(title: str) -> str:
    return title.strip().lower().replace("(", "").replace(")", "")


def _normalize_device_type(value: str | None) -> str:
    """Normalize device type aliases to canonical internal ids."""
    normalized = str(value or "legacy").strip().lower().replace("-", "_")
    if normalized == "ex3301":
        return "ex3301_t0"
    return normalized


def _leaf_values(data: Mapping | None) -> dict[str, object]:
    if not data:
        return {}
    flat = _flatten_value(data)
    leafs: dict[str, object] = {}
    for path, value in flat.items():
        leaf = path.split(".")[-1]
        if leaf not in leafs:
            leafs[leaf] = value
    return leafs


def _ex3301_wifi_signature(data: Mapping | None) -> tuple[tuple[str, bool, bool, str], ...]:
    """Return a stable signature of EX3301 WiFi radio state for reload detection."""
    if not data:
        return ()
    flat = _flatten_value(data)
    radios: dict[str, dict[str, object]] = {}
    for key, value in flat.items():
        if ".WiFiInfo." not in key:
            continue
        prefix, leaf = key.rsplit(".", 1)
        radios.setdefault(prefix, {})[leaf] = value

    normalized: list[tuple[str, bool, bool, str]] = []
    for prefix, fields in radios.items():
        slot = prefix.split(".")[-1]
        enabled = bool(fields.get("Enable"))
        is_main = bool(fields.get("X_ZYXEL_MainSSID"))
        band = str(fields.get("OperatingFrequencyBand") or "").strip()
        normalized.append((slot, enabled, is_main, band))
    return tuple(sorted(normalized))


def _detected_model_from_data(entry: ConfigEntry, data: Mapping | None) -> str:
    leafs = _leaf_values(data)
    model = (
        leafs.get("ModelName")
        or leafs.get("ProductClass")
        or leafs.get("HardwareVersion")
        or entry.data.get("model")
        or entry.data.get(CONF_DEVICE_TYPE, "")
        or _entry_host(entry)
    )
    return str(model).upper().replace("_", "-")


def _should_update_title_to_model(entry: ConfigEntry, model_title: str) -> bool:
    normalized_title = _hostish_title(entry.title)
    normalized_model = _hostish_title(model_title)
    host = _entry_host(entry).lower()
    device_type = str(entry.data.get(CONF_DEVICE_TYPE, "")).lower()
    defaults = {
        host,
        device_type,
        device_type.upper().lower(),
        f"{host}:80",
        f"{host}:443",
        f"zyxel {host}",
        f"zyxel {device_type}",
        f"zyxel {device_type.upper()}".lower(),
        f"zyxel {host}:80",
        f"zyxel {host}:443",
        "english",
        "zyxel english",
        f"zyxel {normalized_model}",
    }
    if entry.title.startswith("Zyxel "):
        return entry.title.removeprefix("Zyxel ") != model_title
    return normalized_title in defaults and entry.title != model_title


def _dashboard_device_cards(hass: HomeAssistant) -> list[dict[str, object]]:
    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)
    grouped: dict[str, dict[str, object]] = {}
    for entity in entity_registry.entities.values():
        if entity.platform != DOMAIN:
            continue
        if not entity.entity_id.startswith(ZYXEL_ENTITY_PREFIXES):
            continue
        if entity.disabled_by is not None:
            continue
        if not entity.device_id:
            continue
        group = grouped.setdefault(
            entity.device_id,
            {"entities": [], "config_entry_id": entity.config_entry_id},
        )
        group["entities"].append(entity.entity_id)
        if not group.get("config_entry_id") and entity.config_entry_id:
            group["config_entry_id"] = entity.config_entry_id

    cards: list[dict[str, object]] = []
    for device_id in sorted(grouped):
        device = device_registry.devices.get(device_id)
        if device and device.disabled_by is not None:
            continue
        group = grouped[device_id]
        if not group["entities"]:
            continue
        heading = _device_title(device)
        config_entry_id = group.get("config_entry_id")
        if config_entry_id:
            config_entry = hass.config_entries.async_get_entry(config_entry_id)
            if config_entry:
                host = _entry_host(config_entry)
                if host:
                    heading = f"{heading} ({host})"
        cards.append(
            {
                "title": heading,
                "column_span": 2,
                "cards": [
                    {
                        "type": "heading",
                        "heading": heading,
                        "heading_style": "subtitle",
                        "icon": "mdi:access-point",
                    },
                    {
                        "type": "entities",
                        "entities": sorted(group["entities"]),
                    },
                ],
            }
        )
    return cards


def _device_detail_sections(hass: HomeAssistant) -> list[dict[str, object]]:
    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)
    sections: list[dict[str, object]] = []
    for device_id in sorted({entity.device_id for entity in entity_registry.entities.values() if entity.platform == DOMAIN and entity.device_id}):
        device = device_registry.devices.get(device_id)
        if device and device.disabled_by is not None:
            continue
        heading = _device_title(device)
        config_entry_id = next(
            (
                entity.config_entry_id
                for entity in entity_registry.entities.values()
                if entity.platform == DOMAIN and entity.device_id == device_id and entity.config_entry_id
            ),
            None,
        )
        if config_entry_id:
            config_entry = hass.config_entries.async_get_entry(config_entry_id)
            if config_entry:
                host = _entry_host(config_entry)
                if host:
                    heading = f"{heading} ({host})"
        summary_entities = _device_summary_entities(hass, device_id)
        device_entities = sorted(
            entity.entity_id
            for entity in entity_registry.entities.values()
            if entity.platform == DOMAIN and entity.device_id == device_id and entity.disabled_by is None
        )
        sections.append(
            {
                "title": heading,
                "column_span": 4,
                "cards": [
                    {
                        "type": "heading",
                        "heading": heading,
                        "heading_style": "title",
                        "icon": "mdi:access-point",
                    },
                    *(
                        [
                            {
                                "type": "entities",
                                "entities": summary_entities,
                            }
                        ]
                        if summary_entities
                        else []
                    ),
                    {
                        "type": "entities",
                        "entities": device_entities,
                    },
                ],
            }
        )
    return sections


async def _ensure_zyxel_dashboard(hass: HomeAssistant, _entity_rows: list[str]) -> None:
    """Create or refresh the shared Zyxel dashboard."""
    dashboards_store = Store[dict[str, object]](hass, 1, ZyXEL_DASHBOARDS_STORAGE_KEY)
    dashboards_data = await dashboards_store.async_load() or {"items": []}
    dashboards_data["items"] = [
        {
            "id": ZyXEL_DASHBOARD_ID,
            "title": "Zyxel Devices",
            "url_path": ZyXEL_DASHBOARD_URL_PATH,
            "icon": "mdi:router",
            "show_in_sidebar": True,
            "require_admin": False,
            "mode": "storage",
        }
    ]
    await dashboards_store.async_save(dashboards_data)

    dashboard_store = Store[dict[str, object]](hass, 1, ZyXEL_DASHBOARD_STORAGE_KEY)
    await dashboard_store.async_save(_zyxel_dashboard_config(hass, _dashboard_device_cards(hass)))
    # Use update=True so re-loading the integration doesn't raise ValueError
    # when the panel is already registered from a previous HA session.
    frontend.async_register_built_in_panel(
        hass,
        "lovelace",
        frontend_url_path=ZyXEL_DASHBOARD_URL_PATH,
        require_admin=False,
        show_in_sidebar=True,
        sidebar_title="Zyxel Devices",
        sidebar_icon="mdi:router",
        config={"mode": "storage"},
        update=True,
    )


def _dashboard_entity_entries(hass: HomeAssistant) -> list[str]:
    registry = er.async_get(hass)
    entries: list[str] = []
    for entity in registry.entities.values():
        if entity.platform != DOMAIN:
            continue
        if not entity.entity_id.startswith(ZYXEL_ENTITY_PREFIXES):
            continue
        if entity.disabled_by is not None:
            continue
        entries.append(entity.entity_id)
    return sorted(entries)


async def _refresh_zyxel_dashboard(hass: HomeAssistant) -> None:
    """Refresh or prune the shared Zyxel dashboard."""
    await _ensure_zyxel_dashboard(hass, _dashboard_entity_entries(hass))


@callback
def _schedule_zyxel_dashboard_refresh(hass: HomeAssistant) -> None:
    """Schedule a dashboard refresh on the event loop."""
    hass.async_create_task(_refresh_zyxel_dashboard(hass))


def _schedule_zyxel_dashboard_refresh_later(hass: HomeAssistant) -> None:
    """Refresh again after the registry settles."""
    hass.loop.call_later(1.0, _schedule_zyxel_dashboard_refresh, hass)


def _flatten_value(value, parent_key: str = "") -> dict:
    items = {}
    if isinstance(value, Mapping):
        for k, v in value.items():
            key = f"{parent_key}.{k}" if parent_key else str(k)
            items.update(_flatten_value(v, key))
    elif isinstance(value, list):
        for idx, v in enumerate(value):
            key = f"{parent_key}.{idx}" if parent_key else str(idx)
            items.update(_flatten_value(v, key))
    else:
        items[parent_key] = value
    return items


def _merge_status_data(router) -> dict:
    """Collect the most useful data objects exposed by a Zyxel device."""
    data = {}

    # Try the generic dashboard OID first; APs expose this while cellular
    # routers still use the legacy cellular/traffic objects below.
    status = router.get_json_object("status")
    if status:
        data.update(status)

    # Preserve the richer legacy data when the device supports it.
    try:
        cellular = router.get_json_object("cellwan_status")
    except Exception:  # pylint: disable=broad-except
        cellular = None
    if cellular:
        data["cellular"] = cellular

    try:
        traffic_obj = router.get_json_object("Traffic_Status")
    except Exception:  # pylint: disable=broad-except
        traffic_obj = None
    if traffic_obj and "ipIface" in traffic_obj and "ipIfaceSt" in traffic_obj:
        traffic = {}
        for iface, iface_st in zip(traffic_obj["ipIface"], traffic_obj["ipIfaceSt"]):
            if isinstance(iface, dict) and "X_ZYXEL_IfName" in iface:
                traffic[iface["X_ZYXEL_IfName"]] = iface_st
        if traffic:
            data["traffic"] = traffic

    try:
        wifi = router.get_json_object("wlan")
    except Exception:  # pylint: disable=broad-except
        wifi = None
    if wifi:
        data["wifi"] = wifi

    return data


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Zyxel integration from a config entry."""


    host = entry.data[CONF_HOST]
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]
    raw_device_type = entry.data.get(CONF_DEVICE_TYPE, "legacy")
    device_type = _normalize_device_type(raw_device_type)
    if raw_device_type != device_type:
        updated_data = dict(entry.data)
        updated_data[CONF_DEVICE_TYPE] = device_type
        hass.config_entries.async_update_entry(entry, data=updated_data)
    if device_type in {"nwa50ax", "ex3301_t0"} and not host.startswith(("http://", "https://")):
        host = f"http://{host}"

    try:
        _LOGGER.debug("Creating Zyxel client for %s", host)
        if device_type == "nwa50ax":
            router = NWA50AXClient(host, username, password)
            await hass.async_add_executor_job(router.login)
            await hass.async_add_executor_job(router.get_status)
        elif device_type == "ex3301_t0":
            router = EX3301T0Client(host, username, password)
            await hass.async_add_executor_job(router.login)
        else:
            router = await hass.async_add_executor_job(
                nr7101.NR7101, host, username, password, {"timeout": 15}
            )
    except Exception as ex:
        _LOGGER.exception("Could not create Zyxel client for %s", host)
        raise ConfigEntryNotReady from ex

    # EX3301 probes each carry a 15s timeout; allow enough wall time for all of them.
    _UPDATE_TIMEOUT = 180 if device_type == "ex3301_t0" else 30

    async def async_update_data():
        """Fetch data from the router."""
        try:
            async with async_timeout.timeout(_UPDATE_TIMEOUT):
                def get_all_data():
                    if device_type in {"nwa50ax", "ex3301_t0"}:
                        return router.get_status()
                    data = _merge_status_data(router)
                    if not data:
                        data = router.get_status()
                    if not data:
                        raise UpdateFailed("No data received from router")
                    return data

                result = await hass.async_add_executor_job(get_all_data)
                if device_type == "ex3301_t0":
                    runtime = hass.data.get(DOMAIN, {}).get(entry.entry_id)
                    if runtime is not None:
                        prev = runtime.get("wifi_signature")
                        new = _ex3301_wifi_signature(result)
                        runtime["wifi_signature"] = new
                        if (
                            prev is not None
                            and prev != new
                            and not runtime.get("wifi_reload_pending")
                        ):
                            runtime["wifi_reload_pending"] = True
                            _LOGGER.info(
                                "EX3301 WiFi state layout changed; reloading entry to refresh entities"
                            )
                            hass.async_create_task(hass.config_entries.async_reload(entry.entry_id))
                return result
        except asyncio.TimeoutError:
            if hasattr(router, "_session_valid"):
                router._session_valid = False
            raise UpdateFailed("Router data fetch timed out")
        except UpdateFailed as err:
            # Re-login and retry once if the EX3301 session has expired.
            if device_type == "ex3301_t0" and "session expired" in str(err).lower():
                _LOGGER.info("EX3301-T0 session expired — re-logging in and retrying")
                try:
                    await hass.async_add_executor_job(router.login)
                    return await hass.async_add_executor_job(router.get_status)
                except Exception as relogin_err:
                    raise UpdateFailed(f"EX3301-T0 re-login failed: {relogin_err}") from relogin_err
            if device_type == "nwa50ax" and "login failed" in str(err).lower():
                _LOGGER.info("NWA50AX login failed — re-logging in and retrying")
                try:
                    await hass.async_add_executor_job(router.login)
                    return await hass.async_add_executor_job(router.get_status)
                except Exception as relogin_err:
                    raise UpdateFailed(f"NWA50AX re-login failed: {relogin_err}") from relogin_err
            raise
        except Exception as err:
            if hasattr(router, "_session_valid"):
                router._session_valid = False
            _LOGGER.exception("Error communicating with Zyxel device at %s", host)
            raise UpdateFailed(f"Error communicating with router: {err}") from err

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=async_update_data,
        update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
    )

    await coordinator.async_config_entry_first_refresh()

    # Keep integration title/data aligned with detected model for existing
    # host-based entries (e.g. "Zyxel 172.16.1.254" -> "EX3301-T0").
    detected_model = _detected_model_from_data(entry, coordinator.data)
    detected_title = detected_model
    updated_data = dict(entry.data)
    data_changed = updated_data.get("model") != detected_model
    if data_changed:
        updated_data["model"] = detected_model
    if _should_update_title_to_model(entry, detected_title):
        hass.config_entries.async_update_entry(
            entry,
            title=detected_title,
            data=updated_data,
        )
    elif data_changed:
        hass.config_entries.async_update_entry(entry, data=updated_data)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "router": router,
        "device_type": device_type,
        "wifi_signature": _ex3301_wifi_signature(coordinator.data) if device_type == "ex3301_t0" else None,
        "wifi_reload_pending": False,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register entity-registry listener (once, for all device types).
    if ZYXEL_DASHBOARD_REFRESH_LISTENER not in hass.data:
        def _handle_entity_registry_update(event) -> None:
            action = event.data.get("action")
            if action not in ("create", "remove", "update"):
                return

            entity_id = event.data.get("entity_id")
            if entity_id and not entity_id.startswith(ZYXEL_ENTITY_PREFIXES):
                return

            # For update events, entity_id may be absent on some HA versions;
            # refresh anyway because a disabled/enabled toggle affects visibility.
            hass.add_job(_schedule_zyxel_dashboard_refresh, hass)

        hass.data[ZYXEL_DASHBOARD_REFRESH_LISTENER] = hass.bus.async_listen(
            er.EVENT_ENTITY_REGISTRY_UPDATED, _handle_entity_registry_update
        )

    # Build the dashboard once all config entries have finished setup.
    # - If HA is still starting up, wait for EVENT_HOMEASSISTANT_STARTED so
    #   all devices have registered their entities before we write the dashboard.
    # - If HA is already running (e.g. user adds a new device), refresh now.
    if not hass.is_running:
        if ZYXEL_HA_STARTED_LISTENER not in hass.data:
            @callback
            def _on_ha_started(event) -> None:
                hass.data.pop(ZYXEL_HA_STARTED_LISTENER, None)
                _schedule_zyxel_dashboard_refresh(hass)

            hass.data[ZYXEL_HA_STARTED_LISTENER] = hass.bus.async_listen_once(
                EVENT_HOMEASSISTANT_STARTED, _on_ha_started
            )
    else:
        await _refresh_zyxel_dashboard(hass)
        _schedule_zyxel_dashboard_refresh_later(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, platform)
                for platform in PLATFORMS
            ]
        )
    )
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        # Remove listener only when the last Zyxel entry is gone.
        if not hass.data[DOMAIN]:
            remove_listener = hass.data.pop(ZYXEL_DASHBOARD_REFRESH_LISTENER, None)
            if remove_listener:
                remove_listener()
        await _refresh_zyxel_dashboard(hass)
        _schedule_zyxel_dashboard_refresh_later(hass)

    return unload_ok
