"""Constants for the Ethex integration."""
from datetime import timedelta

DOMAIN = "ethex"

CONF_USERNAME = "username"
CONF_PASSWORD = "password"

BASE_URL = "https://www.ethex.org.uk"
LOGIN_URL = f"{BASE_URL}/login"
PORTFOLIO_URL = f"{BASE_URL}/investor/portfolios"

DEFAULT_SCAN_INTERVAL = timedelta(minutes=15)

ACCOUNT_MAIN = "main"
ACCOUNT_IFISA = "ifisa"

# Query params used to select which account's detail is rendered server-side
# in #js-main-content-partial. currencyId=1 is assumed to be GBP (the only
# currency observed so far).
ACCOUNT_QUERY_PARAMS = {
    ACCOUNT_MAIN: {"ifisa": "false", "currencyId": "1"},
    ACCOUNT_IFISA: {"ifisa": "true", "currencyId": "1"},
}

# Holdings tabs inside .si-portfolio-investments-tabs, keyed by the
# `role="tabpanel"` element id.
HOLDING_TABS = {
    "investments": "current",
    "past-investments": "repaid",
    "cancelled-or-refunded-investments": "cancelled_or_refunded",
}

# Whether to auto-create a Lovelace dashboard for this integration. Offered
# as a config flow step (and later toggleable via the options flow).
CONF_CREATE_DASHBOARD = "create_dashboard"
DEFAULT_CREATE_DASHBOARD = True
