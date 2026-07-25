"""Build the Lovelace card/view config for the Ethex dashboard.

Kept free of any `homeassistant` imports so it can be unit tested directly,
given a plain list of entity ids. The actual writing to Lovelace storage
lives in `dashboard.py`, which does depend on Home Assistant internals.
"""
from __future__ import annotations

DASHBOARD_URL_PATH = "ethex"
DASHBOARD_TITLE = "Ethex Investment Platform"
DASHBOARD_ICON = "mdi:chart-line"

_HOLDINGS_SENSOR_SUFFIX = "current_investments"


def build_dashboard_config(entity_ids: list[str]) -> dict:
    """Build a Lovelace dashboard config (a single view) from entity ids.

    All sensor entities are listed in an "entities" card, except the
    "Current investments" sensor (identified by its unique_id/entity_id
    suffix), which instead gets a markdown card templated off its
    `holdings` attribute so each holding shows up as a readable line.
    """
    entity_ids = sorted(entity_ids)
    holdings_entity = next(
        (eid for eid in entity_ids if eid.endswith(_HOLDINGS_SENSOR_SUFFIX)), None
    )
    overview_entities = [eid for eid in entity_ids if eid != holdings_entity]

    cards: list[dict] = []

    if overview_entities:
        cards.append(
            {
                "type": "entities",
                "title": "Portfolio overview",
                "entities": overview_entities,
            }
        )

    if holdings_entity:
        cards.append(_holdings_card(holdings_entity))

    return {
        "views": [
            {
                "title": DASHBOARD_TITLE,
                "path": "default_view",
                "icon": DASHBOARD_ICON,
                "cards": cards,
            }
        ]
    }


def _holdings_card(holdings_entity: str) -> dict:
    """A markdown card listing each holding from the sensor's attribute.

    The `holdings` attribute is a list of dicts with a "status" key plus
    whatever `data-title` fields were parsed from the row (typically
    "Name" and, per parser.py's caveat about unverified populated-row
    structure, possibly "Original Investment"/"Current Investment"/
    "Order status" or similar).
    """
    content = (
        "{% set holdings = state_attr('" + holdings_entity + "', 'holdings') %}"
        "{% if holdings %}"
        "{% for h in holdings %}"
        "- **{{ h.Name }}** ({{ h.status }})"
        "{% if h.get('Current Investment') %} — {{ h['Current Investment'] }}{% endif %}"
        "{% if h.get('Order status') %} · {{ h['Order status'] }}{% endif %}\n"
        "{% endfor %}"
        "{% else %}"
        "No holdings found.\n"
        "{% endif %}"
    )
    return {
        "type": "markdown",
        "title": "Current investments",
        "content": content,
    }
