from __future__ import annotations

import datetime as dt
import urllib.parse

import voluptuous as vol

from homeassistant import config_entries

from .client import GitHubBackupClient, GitHubError
from .const import (
    CONF_BACKUP_INTERVAL_HOURS,
    CONF_EXTRA_IGNORE_PATTERNS,
    CONF_GITHUB_CLIENT_ID,
    CONF_GITHUB_TOKEN,
    CONF_IGNORE_PATTERNS,
    CONF_REPOSITORY,
    CONF_SYNC_START_TIME,
    DEFAULT_BACKUP_INTERVAL_HOURS,
    DEFAULT_IGNORE_PATTERNS,
    DEFAULT_SYNC_START_TIME,
    DOMAIN,
)

DEFAULT_REPOSITORY_NAME = "ha-config"


class GitHubConfigSyncFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._client_id: str | None = None
        self._token: str | None = None
        self._interval_hours = DEFAULT_BACKUP_INTERVAL_HOURS
        self._start_time = DEFAULT_SYNC_START_TIME
        self._ignore_patterns = list(DEFAULT_IGNORE_PATTERNS)
        self._extra_ignore_patterns = ""
        self._device_flow: dict[str, str] | None = None

    async def async_step_user(self, user_input=None):
        errors: dict[str, str] = {}
        if user_input is not None:
            self._client_id = user_input[CONF_GITHUB_CLIENT_ID]
            self._interval_hours = user_input[CONF_BACKUP_INTERVAL_HOURS]
            self._start_time = user_input[CONF_SYNC_START_TIME]
            self._ignore_patterns = [
                pattern.strip()
                for pattern in user_input[CONF_IGNORE_PATTERNS].splitlines()
                if pattern.strip()
            ]
            self._extra_ignore_patterns = user_input[CONF_EXTRA_IGNORE_PATTERNS]
            try:
                self._device_flow = await GitHubBackupClient(
                    self.hass, token="", repository="octocat/hello-world"
                ).async_start_device_flow(self._client_id)
            except GitHubError:
                errors["base"] = "invalid_auth"
            else:
                return await self.async_step_device_auth()

        schema = vol.Schema(
            {
                vol.Required(CONF_GITHUB_CLIENT_ID): str,
                vol.Required(
                    CONF_BACKUP_INTERVAL_HOURS,
                    default=self._interval_hours,
                ): vol.All(vol.Coerce(int), vol.Range(min=1)),
                vol.Required(
                    CONF_SYNC_START_TIME,
                    default=self._start_time,
                ): vol.All(vol.Match(r"^\d{2}:\d{2}$")),
                vol.Optional(
                    CONF_IGNORE_PATTERNS,
                    default="\n".join(self._ignore_patterns),
                ): str,
                vol.Optional(CONF_EXTRA_IGNORE_PATTERNS, default=""): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_device_auth(self, user_input=None):
        if self._device_flow is None:
            return await self.async_step_user()

        if user_input is not None:
            client = GitHubBackupClient(
                self.hass, token="", repository="octocat/hello-world"
            )
            try:
                self._token = await client.async_exchange_device_code(
                    self._client_id,
                    self._device_flow["device_code"],
                    interval=int(self._device_flow.get("interval", "5")),
                )
            except GitHubError:
                return self.async_show_form(
                    step_id="device_auth",
                    data_schema=vol.Schema({vol.Required("confirm"): bool}),
                    errors={"base": "invalid_auth"},
                )
            return await self.async_step_repo_choice()

        verification_uri = self._device_flow.get("verification_uri")
        user_code = self._device_flow.get("user_code")
        schema = vol.Schema({vol.Required("confirm", default=True): bool})
        return self.async_show_form(
            step_id="device_auth",
            data_schema=schema,
            description_placeholders={
                "verification_uri": verification_uri,
                "user_code": user_code,
            },
        )

    async def async_step_repo_choice(self, user_input=None):
        if user_input is not None:
            if user_input["mode"] == "create":
                return await self.async_step_create_repo()
            return await self.async_step_existing_repo()

        schema = vol.Schema({vol.Required("mode"): vol.In(["create", "existing"])})
        return self.async_show_form(step_id="repo_choice", data_schema=schema)

    async def async_step_create_repo(self, user_input=None):
        errors: dict[str, str] = {}
        if user_input is not None:
            client = GitHubBackupClient(
                self.hass, token=self._token, repository="octocat/hello-world"
            )
            try:
                repo = await client.async_create_repo(
                    name=DEFAULT_REPOSITORY_NAME,
                    private=user_input["private"],
                    description=user_input.get("description"),
                )
            except GitHubError:
                errors["base"] = "cannot_create"
            else:
                return self.async_create_entry(
                    title=repo["full_name"],
                    data=self._build_entry_data(repo["full_name"]),
                )

        schema = vol.Schema(
            {
                vol.Optional("private", default=True): bool,
                vol.Optional("description", default="Home Assistant config sync"): str,
            }
        )
        return self.async_show_form(
            step_id="create_repo", data_schema=schema, errors=errors
        )

    async def async_step_existing_repo(self, user_input=None):
        errors: dict[str, str] = {}
        if user_input is not None:
            repository = user_input["repository"].strip()
            if "/" not in repository:
                errors["repository"] = "invalid_repository"
            else:
                return self.async_create_entry(
                    title=repository,
                    data=self._build_entry_data(repository),
                )

        schema = vol.Schema({vol.Required(CONF_REPOSITORY): str})
        return self.async_show_form(
            step_id="existing_repo", data_schema=schema, errors=errors
        )

    def _build_entry_data(self, repository: str) -> dict[str, object]:
        return {
            CONF_GITHUB_CLIENT_ID: self._client_id,
            CONF_GITHUB_TOKEN: self._token,
            CONF_REPOSITORY: repository,
            CONF_BACKUP_INTERVAL_HOURS: self._interval_hours,
            CONF_SYNC_START_TIME: self._start_time,
            CONF_IGNORE_PATTERNS: self._ignore_patterns,
            CONF_EXTRA_IGNORE_PATTERNS: [
                line.strip()
                for line in self._extra_ignore_patterns.splitlines()
                if line.strip()
            ],
        }
