"""Config flow for Cross Battery Charge Guard."""

from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector

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
    DOMAIN,
)

ENTITY_SELECTOR = selector.EntitySelector(selector.EntitySelectorConfig())


def _step_schema(defaults: dict[str, str | bool]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_CREATE_DASHBOARD, default=defaults.get(CONF_CREATE_DASHBOARD, DEFAULT_CREATE_DASHBOARD)): bool,
            vol.Required(CONF_DASHBOARD_TITLE, default=defaults.get(CONF_DASHBOARD_TITLE, DEFAULT_DASHBOARD_TITLE)): str,
            vol.Required(CONF_DASHBOARD_URL_PATH, default=defaults.get(CONF_DASHBOARD_URL_PATH, DEFAULT_DASHBOARD_URL_PATH)): str,
            vol.Required(CONF_BATTERY_A_NAME, default=defaults.get(CONF_BATTERY_A_NAME, "Battery A")): str,
            vol.Required(CONF_BATTERY_A_SOC, default=defaults.get(CONF_BATTERY_A_SOC, "")): ENTITY_SELECTOR,
            vol.Required(CONF_BATTERY_A_POWER, default=defaults.get(CONF_BATTERY_A_POWER, "")): ENTITY_SELECTOR,
            vol.Required(CONF_BATTERY_A_CURRENT_LIMIT, default=defaults.get(CONF_BATTERY_A_CURRENT_LIMIT, "")): ENTITY_SELECTOR,
            vol.Required(CONF_BATTERY_A_HOUSE_LOAD, default=defaults.get(CONF_BATTERY_A_HOUSE_LOAD, "")): ENTITY_SELECTOR,
            vol.Required(CONF_BATTERY_B_NAME, default=defaults.get(CONF_BATTERY_B_NAME, "Battery B")): str,
            vol.Required(CONF_BATTERY_B_SOC, default=defaults.get(CONF_BATTERY_B_SOC, "")): ENTITY_SELECTOR,
            vol.Required(CONF_BATTERY_B_POWER, default=defaults.get(CONF_BATTERY_B_POWER, "")): ENTITY_SELECTOR,
            vol.Required(CONF_BATTERY_B_CURRENT_LIMIT, default=defaults.get(CONF_BATTERY_B_CURRENT_LIMIT, "")): ENTITY_SELECTOR,
            vol.Required(CONF_BATTERY_B_HOUSE_LOAD, default=defaults.get(CONF_BATTERY_B_HOUSE_LOAD, "")): ENTITY_SELECTOR,
        }
    )


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(
                title=user_input.get(CONF_DASHBOARD_TITLE, DEFAULT_DASHBOARD_TITLE),
                data=user_input,
            )

        return self.async_show_form(step_id="user", data_schema=_step_schema({}))


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Options flow for editing the integration."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        defaults = dict(self.config_entry.data)
        defaults.update(self.config_entry.options)
        return self.async_show_form(step_id="init", data_schema=_step_schema(defaults))


async def async_get_options_flow(config_entry: config_entries.ConfigEntry):
    return OptionsFlowHandler(config_entry)
