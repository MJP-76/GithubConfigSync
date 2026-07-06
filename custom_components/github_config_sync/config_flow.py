from __future__ import annotations

import datetime as dt

from aiohttp import web
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.http import HomeAssistantView

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
    GITHUB_OAUTH_CLIENT_ID,
)

DEFAULT_REPOSITORY_NAME = "ha-config"
AUTH_VIEW_KEY = "auth_view_registered"
AUTH_FLOW_MAP_KEY = "auth_flow_map"
AUTH_START_PATH = "/api/github_config_sync/auth/start"


class GitHubConfigSyncFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._client_id: str | None = GITHUB_OAUTH_CLIENT_ID or None
        self._token: str | None = None
        self._interval_hours = DEFAULT_BACKUP_INTERVAL_HOURS
        self._start_time = DEFAULT_SYNC_START_TIME
        self._ignore_patterns = list(DEFAULT_IGNORE_PATTERNS)
        self._extra_ignore_patterns = ""
        self._device_flow: dict[str, object] | None = None

    async def async_step_user(self, user_input=None):
        errors: dict[str, str] = {}
        if user_input is not None:
            start_time = user_input[CONF_SYNC_START_TIME].strip()
            if not _is_valid_hh_mm(start_time):
                errors[CONF_SYNC_START_TIME] = "invalid_time"
            else:
                self._client_id = GITHUB_OAUTH_CLIENT_ID or user_input.get(
                    CONF_GITHUB_CLIENT_ID, ""
                ).strip()
                if not self._client_id:
                    errors[CONF_GITHUB_CLIENT_ID] = "required"
                else:
                    self._interval_hours = user_input[CONF_BACKUP_INTERVAL_HOURS]
                    self._start_time = start_time
                    self._ignore_patterns = [
                        pattern.strip()
                        for pattern in user_input[CONF_IGNORE_PATTERNS].splitlines()
                        if pattern.strip()
                    ]
                    self._extra_ignore_patterns = user_input[CONF_EXTRA_IGNORE_PATTERNS]
                    try:
                        _ensure_auth_view(self.hass)
                        self._device_flow = await GitHubBackupClient(
                            self.hass, token="", repository="octocat/hello-world"
                        ).async_start_device_flow(self._client_id)
                        self.hass.data.setdefault(DOMAIN, {}).setdefault(
                            AUTH_FLOW_MAP_KEY, {}
                        )[self.flow_id] = self._device_flow
                    except GitHubError:
                        errors["base"] = "invalid_auth"
                    else:
                        return await self.async_step_device_auth()

        schema_data: dict[vol.Marker, object] = {
            vol.Required(
                CONF_BACKUP_INTERVAL_HOURS,
                default=self._interval_hours,
            ): vol.All(vol.Coerce(int), vol.Range(min=1)),
            vol.Required(
                CONF_SYNC_START_TIME,
                default=self._start_time,
            ): str,
            vol.Optional(
                CONF_IGNORE_PATTERNS,
                default="\n".join(self._ignore_patterns),
            ): str,
            vol.Optional(CONF_EXTRA_IGNORE_PATTERNS, default=""): str,
        }
        if not GITHUB_OAUTH_CLIENT_ID:
            schema_data = {
                vol.Required(
                    CONF_GITHUB_CLIENT_ID,
                    default=self._client_id or "",
                ): str,
                **schema_data,
            }

        schema = vol.Schema(schema_data)
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_device_auth(self, user_input=None):
        if self._device_flow is None:
            return await self.async_step_user()

        if user_input is not None:
            return self.async_external_step_done(next_step_id="device_auth_done")

        return self.async_external_step(
            step_id="device_auth",
            url=f"{AUTH_START_PATH}?flow_id={self.flow_id}",
        )

    async def async_step_device_auth_done(self, _user_input=None):
        if self._device_flow is None:
            return await self.async_step_user()

        client = GitHubBackupClient(self.hass, token="", repository="octocat/hello-world")
        try:
            self._token = await client.async_exchange_device_code(
                self._client_id,
                str(self._device_flow["device_code"]),
                interval=int(self._device_flow.get("interval", 5)),
            )
        except GitHubError:
            _clear_auth_flow(self.hass, self.flow_id)
            return self.async_abort(reason="invalid_auth")

        _clear_auth_flow(self.hass, self.flow_id)
        return await self.async_step_repo_choice()

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
            CONF_BACKUP_INTERVAL_HOURS: self._interval_hours,
            CONF_SYNC_START_TIME: self._start_time,
            CONF_IGNORE_PATTERNS: self._ignore_patterns,
            CONF_EXTRA_IGNORE_PATTERNS: [
                line.strip()
                for line in self._extra_ignore_patterns.splitlines()
                if line.strip()
            ],
            **(
                {CONF_GITHUB_CLIENT_ID: self._client_id}
                if not GITHUB_OAUTH_CLIENT_ID
                else {}
            ),
        }


def _is_valid_hh_mm(value: str) -> bool:
    try:
        parsed = dt.time.fromisoformat(value)
    except ValueError:
        return False
    return value == parsed.strftime("%H:%M")


def _ensure_auth_view(hass) -> None:
    domain_data = hass.data.setdefault(DOMAIN, {})
    if domain_data.get(AUTH_VIEW_KEY):
        return
    hass.http.register_view(GitHubAuthStartView)
    domain_data[AUTH_VIEW_KEY] = True


def _clear_auth_flow(hass, flow_id: str) -> None:
    flow_map = hass.data.setdefault(DOMAIN, {}).setdefault(AUTH_FLOW_MAP_KEY, {})
    flow_map.pop(flow_id, None)


def _build_github_device_url(device_flow: dict[str, object]) -> str:
    base = str(device_flow.get("verification_uri") or "https://github.com/login/device")
    user_code = str(device_flow.get("user_code") or "").strip()
    if not user_code:
        return base
    return f"{base}?user_code={user_code}"


class GitHubAuthStartView(HomeAssistantView):
    """Redirect config flow users to GitHub device login page."""

    url = AUTH_START_PATH
    name = "api:github_config_sync:auth_start"
    requires_auth = True

    async def get(self, request):
        flow_id = request.query.get("flow_id")
        if not flow_id:
            raise web.HTTPBadRequest(text="Missing flow_id")

        flow_map = request.app["hass"].data.setdefault(DOMAIN, {}).setdefault(
            AUTH_FLOW_MAP_KEY, {}
        )
        device_flow = flow_map.get(flow_id)
        if not device_flow:
            raise web.HTTPNotFound(text="Flow not found or expired")

        raise web.HTTPFound(_build_github_device_url(device_flow))
