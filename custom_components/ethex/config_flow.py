"""Config flow for the Ethex integration."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import EthexAuthError, EthexClient, EthexConnectionError
from .const import (
    CONF_CREATE_DASHBOARD,
    CONF_PASSWORD,
    CONF_USERNAME,
    DEFAULT_CREATE_DASHBOARD,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


async def _validate_login(hass: HomeAssistant, username: str, password: str) -> None:
    """Attempt a login; raises EthexAuthError/EthexConnectionError on failure.

    Uses Home Assistant's shared client session. It must NOT be closed here —
    it's owned and reused by HA/other integrations for the lifetime of the
    process.
    """
    session = async_get_clientsession(hass)
    client = EthexClient(session, username, password)
    await client.async_login()


class EthexConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Ethex."""

    VERSION = 1

    def __init__(self) -> None:
        self._credentials: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the initial step: collect and validate credentials."""
        errors: dict[str, str] = {}

        if user_input is not None:
            username = user_input[CONF_USERNAME]
            password = user_input[CONF_PASSWORD]

            await self.async_set_unique_id(username.lower())
            self._abort_if_unique_id_configured()

            try:
                await _validate_login(self.hass, username, password)
            except EthexAuthError:
                errors["base"] = "invalid_auth"
            except EthexConnectionError:
                errors["base"] = "cannot_connect"
            except aiohttp.ClientError:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception during Ethex login validation")
                errors["base"] = "unknown"
            else:
                self._credentials = user_input
                return await self.async_step_dashboard()

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_dashboard(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Offer to auto-create a Lovelace dashboard for the portfolio sensors."""
        if user_input is not None:
            data = {**self._credentials, CONF_CREATE_DASHBOARD: user_input[CONF_CREATE_DASHBOARD]}
            return self.async_create_entry(title=self._credentials[CONF_USERNAME], data=data)

        schema = vol.Schema(
            {vol.Required(CONF_CREATE_DASHBOARD, default=DEFAULT_CREATE_DASHBOARD): bool}
        )
        return self.async_show_form(step_id="dashboard", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> EthexOptionsFlow:
        """Get the options flow for this handler."""
        return EthexOptionsFlow(config_entry)


class EthexOptionsFlow(config_entries.OptionsFlow):
    """Options flow allowing the dashboard preference to be changed later."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self._config_entry.options.get(
            CONF_CREATE_DASHBOARD,
            self._config_entry.data.get(CONF_CREATE_DASHBOARD, DEFAULT_CREATE_DASHBOARD),
        )
        schema = vol.Schema({vol.Required(CONF_CREATE_DASHBOARD, default=current): bool})
        return self.async_show_form(step_id="init", data_schema=schema)

