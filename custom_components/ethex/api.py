"""Async client for logging into Ethex and fetching portfolio pages."""
from __future__ import annotations

import logging
import re

import aiohttp

from .const import ACCOUNT_QUERY_PARAMS, LOGIN_URL, PORTFOLIO_URL

_LOGGER = logging.getLogger(__name__)

_TOKEN_RE = re.compile(
    r'name="__RequestVerificationToken"[^>]*value="([^"]+)"'
)


class EthexAuthError(Exception):
    """Raised when login fails (bad credentials or unexpected response)."""


class EthexConnectionError(Exception):
    """Raised when Ethex cannot be reached."""


class EthexClient:
    """Handles authentication and page retrieval for ethex.org.uk."""

    def __init__(self, session: aiohttp.ClientSession, username: str, password: str) -> None:
        self._session = session
        self._username = username
        self._password = password
        self._logged_in = False

    async def async_login(self) -> None:
        """Log in, obtaining and submitting the anti-forgery token."""
        try:
            async with self._session.get(LOGIN_URL) as resp:
                resp.raise_for_status()
                html = await resp.text()
        except aiohttp.ClientError as err:
            raise EthexConnectionError(f"Could not reach Ethex login page: {err}") from err

        match = _TOKEN_RE.search(html)
        if not match:
            raise EthexAuthError("Could not find anti-forgery token on login page")
        token = match.group(1)

        payload = {
            "__RequestVerificationToken": token,
            "UserName": self._username,
            "Password": self._password,
        }

        try:
            async with self._session.post(LOGIN_URL, data=payload, allow_redirects=True) as resp:
                resp.raise_for_status()
                final_url = str(resp.url)
                html = await resp.text()
        except aiohttp.ClientError as err:
            raise EthexConnectionError(f"Could not reach Ethex login endpoint: {err}") from err

        if "/login" in final_url.lower() or "UserName" in html:
            raise EthexAuthError("Invalid username or password")

        self._logged_in = True

    async def async_get_portfolio_page(self, account: str) -> str:
        """Fetch the /investor/portfolios page for the given account.

        `account` must be a key in ACCOUNT_QUERY_PARAMS ("main" or "ifisa").
        """
        if not self._logged_in:
            await self.async_login()

        params = ACCOUNT_QUERY_PARAMS[account]
        try:
            async with self._session.get(PORTFOLIO_URL, params=params) as resp:
                resp.raise_for_status()
                return await resp.text()
        except aiohttp.ClientError as err:
            raise EthexConnectionError(f"Could not reach Ethex portfolio page: {err}") from err
