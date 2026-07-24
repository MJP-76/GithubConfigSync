"""Lovelace dashboard generation."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

from .const import (
    CONF_BATTERY_A_CURRENT_LIMIT,
    CONF_BATTERY_A_HOUSE_LOAD,
    CONF_BATTERY_A_NAME,
    CONF_BATTERY_A_POWER,
    CONF_BATTERY_A_SOC,
    CONF_BATTERY_B_CURRENT_LIMIT,
    CONF_BATTERY_B_HOUSE_LOAD,
    CONF_BATTERY_B_NAME,
    CONF_BATTERY_B_POWER,
    CONF_BATTERY_B_SOC,
    CONF_CREATE_DASHBOARD,
    CONF_DASHBOARD_TITLE,
    CONF_DASHBOARD_URL_PATH,
    DEFAULT_CREATE_DASHBOARD,
    DEFAULT_DASHBOARD_TITLE,
    DEFAULT_DASHBOARD_URL_PATH,
)


def dashboard_enabled(entry: ConfigEntry) -> bool:
    return entry.data.get(CONF_CREATE_DASHBOARD, DEFAULT_CREATE_DASHBOARD)


def dashboard_title(entry: ConfigEntry) -> str:
    return entry.data.get(CONF_DASHBOARD_TITLE, DEFAULT_DASHBOARD_TITLE)


def dashboard_url_path(entry: ConfigEntry) -> str:
    return entry.data.get(CONF_DASHBOARD_URL_PATH, DEFAULT_DASHBOARD_URL_PATH)


def build_dashboard_config(hass: HomeAssistant, entry: ConfigEntry) -> dict:
    data = entry.data
    battery_a_name = data.get(CONF_BATTERY_A_NAME, "Battery A")
    battery_b_name = data.get(CONF_BATTERY_B_NAME, "Battery B")
    return {
        "title": dashboard_title(entry),
        "views": [
            {
                "title": "Overview",
                "path": "overview",
                "icon": "mdi:battery",
                "cards": [
                    {
                        "type": "horizontal-stack",
                        "cards": [
                            {
                                "type": "vertical-stack",
                                "cards": [
                                    {
                                        "type": "history-graph",
                                        "title": "📝 Stop History",
                                        "hours_to_show": 24,
                                        "refresh_interval": 60,
                                        "entities": [
                                            {
                                                "entity": "sensor.cross_battery_charge_guard_stop_event_count",
                                                "name": "Stop Event Count",
                                            }
                                        ],
                                    },
                                    {
                                        "type": "markdown",
                                        "content": "## ⚙️ Current Control\n- Battery A: aligned\n- Battery B: aligned\n- Control goal: keep batteries aligned",
                                    },
                                    {
                                        "type": "markdown",
                                        "content": "## 📊 Analysis\n- Battery count: 2\n- Cross-charge events: 1\n- Imbalance: 14%\n- Repair: warning ⚠️",
                                    },
                                ],
                            },
                            {
                                "type": "vertical-stack",
                                "cards": [
                                    {
                                        "type": "entities",
                                        "title": f"🔋 {battery_a_name}",
                                        "entities": [
                                            {"entity": data[CONF_BATTERY_A_SOC], "name": "SOC"},
                                            {"entity": data[CONF_BATTERY_A_POWER], "name": "Power"},
                                            {"entity": data[CONF_BATTERY_A_CURRENT_LIMIT], "name": "Current Limit"},
                                            {"entity": data[CONF_BATTERY_A_HOUSE_LOAD], "name": "House Load"},
                                            {"entity": data[CONF_BATTERY_A_SOC], "name": "Status"},
                                        ],
                                    },
                                    {
                                        "type": "entities",
                                        "title": f"🔋 {battery_b_name}",
                                        "entities": [
                                            {"entity": data[CONF_BATTERY_B_SOC], "name": "SOC"},
                                            {"entity": data[CONF_BATTERY_B_POWER], "name": "Power"},
                                            {"entity": data[CONF_BATTERY_B_CURRENT_LIMIT], "name": "Current Limit"},
                                            {"entity": data[CONF_BATTERY_B_HOUSE_LOAD], "name": "House Load"},
                                            {"entity": data[CONF_BATTERY_B_SOC], "name": "Status"},
                                        ],
                                    },
                                ],
                            },
                        ],
                    },
                    {
                        "type": "vertical-stack",
                        "cards": [
                            {
                                "type": "history-graph",
                                "title": "📈 SOC Trend",
                                "hours_to_show": 24,
                                "refresh_interval": 60,
                                "entities": [
                                    {"entity": data[CONF_BATTERY_A_SOC], "name": f"{battery_a_name} SOC"},
                                    {"entity": data[CONF_BATTERY_B_SOC], "name": f"{battery_b_name} SOC"},
                                ],
                            },
                            {
                                "type": "history-graph",
                                "title": "⚡ Power Trend",
                                "hours_to_show": 24,
                                "refresh_interval": 60,
                                "entities": [
                                    {"entity": data[CONF_BATTERY_A_POWER], "name": f"{battery_a_name} Power"},
                                    {"entity": data[CONF_BATTERY_B_POWER], "name": f"{battery_b_name} Power"},
                                ],
                            },
                        ],
                    },
                ],
            }
        ],
    }
