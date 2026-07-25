"""Data update coordinator for the Ethex integration."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import EthexAuthError, EthexClient, EthexConnectionError
from .const import ACCOUNT_IFISA, ACCOUNT_MAIN, DEFAULT_SCAN_INTERVAL, HOLDING_TABS
from .parser import AccountDetail, Holding, PortfolioSummary, parse_account_detail, parse_holdings, parse_summary

_LOGGER = logging.getLogger(__name__)


@dataclass
class EthexData:
    """A single fetch's worth of portfolio data."""

    summary: PortfolioSummary
    main: AccountDetail
    ifisa: AccountDetail
    holdings: list[Holding]


class EthexCoordinator(DataUpdateCoordinator[EthexData]):
    """Fetches and parses Ethex portfolio data on a schedule."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: EthexClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="Ethex Investment Platform portfolio",
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        self._entry = entry
        self._client = client

    async def _async_update_data(self) -> EthexData:
        try:
            main_html = await self._client.async_get_portfolio_page(ACCOUNT_MAIN)
            ifisa_html = await self._client.async_get_portfolio_page(ACCOUNT_IFISA)
        except EthexAuthError as err:
            raise UpdateFailed(f"Authentication failed: {err}") from err
        except EthexConnectionError as err:
            raise UpdateFailed(f"Error communicating with Ethex: {err}") from err

        summary = parse_summary(main_html)
        main_detail = parse_account_detail(main_html)
        ifisa_detail = parse_account_detail(ifisa_html)
        holdings = parse_holdings(main_html, HOLDING_TABS)

        return EthexData(
            summary=summary,
            main=main_detail,
            ifisa=ifisa_detail,
            holdings=holdings,
        )
