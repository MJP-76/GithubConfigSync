from __future__ import annotations

import os

import voluptuous as vol

from homeassistant import config_entries

from .client import GitHubBackupClient, GitHubError
from .const import (
    CONF_BACKUP_INTERVAL_MINUTES,
    CONF_EXTRA_IGNORE_PATTERNS,
    CONF_GITHUB_TOKEN,
    CONF_IGNORE_PATTERNS,
    CONF_REPOSITORY,
    DEFAULT_BACKUP_INTERVAL_MINUTES,
    DEFAULT_IGNORE_PATTERNS,
    DOMAIN,
)

DEFAULT_REPOSITORY_NAME = "ha-config"


class GitHubConfigSyncFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._token: str | None = None
        self._interval_minutes = DEFAULT_BACKUP_INTERVAL_MINUTES
        self._ignore_patterns = list(DEFAULT_IGNORE_PATTERNS)
        self._extra_ignore_patterns = ""

    async def async_step_user(self, user_input=None):
        errors: dict[str, str] = {}
        if user_input is not None:
            self._token = user_input[CONF_GITHUB_TOKEN]
            self._interval_minutes = user_input[CONF_BACKUP_INTERVAL_MINUTES]
            self._ignore_patterns = [
                pattern.strip()
                for pattern in user_input[CONF_IGNORE_PATTERNS].splitlines()
                if pattern.strip()
            ]
            self._extra_ignore_patterns = user_input[CONF_EXTRA_IGNORE_PATTERNS]

            client = GitHubBackupClient(
                self.hass, token=self._token, repository="octocat/hello-world"
            )
            try:
                await client.async_validate()
            except GitHubError:
                errors["base"] = "invalid_auth"
            else:
                return await self.async_step_repo_choice()

        schema = vol.Schema(
            {
                vol.Required(CONF_GITHUB_TOKEN): str,
                vol.Required(
                    CONF_BACKUP_INTERVAL_MINUTES,
                    default=self._interval_minutes,
                ): vol.All(vol.Coerce(int), vol.Range(min=1)),
                vol.Optional(
                    CONF_IGNORE_PATTERNS,
                    default="\n".join(self._ignore_patterns),
                ): str,
                vol.Optional(CONF_EXTRA_IGNORE_PATTERNS, default=""): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

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
            CONF_GITHUB_TOKEN: self._token,
            CONF_REPOSITORY: repository,
            CONF_BACKUP_INTERVAL_MINUTES: self._interval_minutes,
            CONF_IGNORE_PATTERNS: self._ignore_patterns,
            CONF_EXTRA_IGNORE_PATTERNS: [
                line.strip()
                for line in self._extra_ignore_patterns.splitlines()
                if line.strip()
            ],
        }
