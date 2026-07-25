"""Parsing of Ethex's authenticated /investor/portfolios page.

The selectors below were reverse-engineered from a real, logged-in copy of
the portfolios page (saved via the browser's "Save as" while the account had
£0.00 balances). The summary card and account-detail markup are taken
verbatim from that capture and should be reliable.

CAVEAT: the account used to capture the page had no holdings, so the
holdings table (`table.si-portfolio-table`) only ever showed a single
empty/placeholder row (` - ` in every cell), and that placeholder row's
`data-title` attributes did not fully match the `<thead>` column headers.
We could not capture what a *populated* row (with real holdings) looks like.

To stay robust against that uncertainty, `parse_holdings` does NOT hardcode
column positions. Instead it reads each `<td data-title="...">` in a row as a
generic key/value pair, and skips rows whose first meaningful cell is empty
or just "-" (i.e. the empty-state placeholder row). This should keep working
even if a populated row has more/different `data-title` columns than the
empty one (e.g. separate "Original Investment" and "Current Investment"
values). This part is INFERRED/UNVERIFIED and may need adjustment once
there are real holdings to test against.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re

from bs4 import BeautifulSoup, Tag

# Matches a GBP currency string like "£1,234.56" or "-£12.00".
_CURRENCY_RE = re.compile(r"-?£\s*[\d,]+(?:\.\d+)?")


def _clean_text(value: str | None) -> str:
    """Collapse whitespace and strip a string pulled from the DOM."""
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def _parse_currency(text: str | None) -> float | None:
    """Parse a GBP currency string (e.g. "£1,234.56") into a float."""
    text = _clean_text(text)
    match = _CURRENCY_RE.search(text)
    if not match:
        return None
    number = match.group(0).replace("£", "").replace(",", "").strip()
    try:
        return float(number)
    except ValueError:
        return None


def _hint_value_pairs(container: Tag) -> dict:
    """Extract all `.si-invest__hint` label / `.si-portfolio__heading` value
    pairs directly under `container`, without recursing into nested
    `.si-invest__hint`/`.si-portfolio__heading` pairs that belong to a
    different logical group (e.g. the holdings table).

    Returns a dict keyed by the cleaned label text, values are the raw
    cleaned text of the paired heading (currency parsing is left to callers,
    since not every heading is a currency value).
    """
    pairs: dict[str, str] = {}
    for hint in container.select(".si-invest__hint"):
        # The value is the sibling `.si-portfolio__heading` within the same
        # `.col` (or `.si-portfolio__col-cash`) wrapper.
        parent = hint.parent
        if parent is None:
            continue
        heading = parent.select_one(".si-portfolio__heading")
        if heading is None:
            continue
        label = _clean_text(hint.get_text())
        pairs[label] = _clean_text(heading.get_text())
    return pairs


@dataclass
class PortfolioSummary:
    """The top-of-page "at a glance" summary card."""

    main_account_value: float | None = None
    ifisa_account_value: float | None = None
    portfolio_total: float | None = None


@dataclass
class AccountDetail:
    """Per-account (main or IFISA) detail section."""

    total: float | None = None
    invested: float | None = None
    cash_balance: float | None = None


@dataclass
class Holding:
    """A single row from a holdings table."""

    status: str
    fields: dict = field(default_factory=dict)

    @property
    def name(self) -> str | None:
        return self.fields.get("Name")


def parse_summary(html: str) -> PortfolioSummary:
    """Parse the `#js-investor-summary-partial` summary card.

    Structure:
        <div id="js-investor-summary-partial">
          <div class="row row--flex si-portfolio-profile-row">
            <div class="col"> ... name/last login, no hint/heading pair ... </div>
            <div class="col">
              <div class="si-invest__hint">Main account</div>
              <div class="si-portfolio__heading">£0.00</div>
            </div>
            <div class="col">
              <div class="si-invest__hint">IFISA account</div>
              <div class="si-portfolio__heading">£0.00</div>
            </div>
            <div class="col">
              <div class="si-invest__hint js-portfolio-account-text">Portfolio total</div>
              <div class="si-portfolio__heading si-portfolio__heading--bold">£0.00</div>
            </div>
          </div>
        </div>
    """
    soup = BeautifulSoup(html, "html.parser")
    partial = soup.select_one("#js-investor-summary-partial")
    if partial is None:
        return PortfolioSummary()

    pairs = _hint_value_pairs(partial)

    # The grand total is additionally identifiable by
    # `.si-portfolio__heading--bold` / `.js-portfolio-account-text`, in case
    # its label text ever changes.
    total_heading = partial.select_one(".si-portfolio__heading--bold")
    portfolio_total = _parse_currency(total_heading.get_text()) if total_heading else None
    if portfolio_total is None:
        portfolio_total = _parse_currency(pairs.get("Portfolio total"))

    return PortfolioSummary(
        main_account_value=_parse_currency(pairs.get("Main account")),
        ifisa_account_value=_parse_currency(pairs.get("IFISA account")),
        portfolio_total=portfolio_total,
    )


def parse_account_detail(html: str) -> AccountDetail:
    """Parse the `#js-main-content-partial` per-account detail section.

    Structure:
        <div id="js-main-content-partial">
          <div class="si-invest__heading-group"> ... "Main account" ... </div>
          <div class="si-portfolio-account-wrapper">
            <div class="row row--flex si-portfolio-profile-row si-portfolio-account-row">
              <div class="col">
                <div class="si-invest__hint">Total</div>
                <div class="si-portfolio__heading"><strong>£0.00</strong></div>
              </div>
              <div class="col">
                <div class="si-invest__hint">Invested</div>
                <div class="si-portfolio__heading">£0.00</div>
              </div>
              <div class="col">
                <div class="si-portfolio__col--highlighted">
                  <div class="si-portfolio__col-cash">
                    <div class="si-invest__hint">Cash balance</div>
                    <div class="si-portfolio__heading">£0.00</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
    """
    soup = BeautifulSoup(html, "html.parser")
    wrapper = soup.select_one(
        "#js-main-content-partial .si-portfolio-account-wrapper"
    )
    if wrapper is None:
        return AccountDetail()

    pairs = _hint_value_pairs(wrapper)

    return AccountDetail(
        total=_parse_currency(pairs.get("Total")),
        invested=_parse_currency(pairs.get("Invested")),
        cash_balance=_parse_currency(pairs.get("Cash balance")),
    )


def _parse_holdings_table(table: Tag, status: str) -> list[Holding]:
    """Generically parse `tr.si-portfolio-table-tr` rows from a single
    holdings table, keyed by each `<td data-title="...">`'s label/value.
    """
    holdings: list[Holding] = []
    for row in table.select("tbody tr.si-portfolio-table-tr"):
        fields: dict = {}
        for cell in row.select("td[data-title]"):
            title = _clean_text(cell.get("data-title"))
            if not title:
                # Skip cells with an empty data-title (e.g. action/icon
                # columns that carry no meaningful data).
                continue
            fields[title] = _clean_text(cell.get_text())

        if not fields:
            continue

        # The empty-state placeholder row has " - " (or blank) in every
        # cell. Use the first parsed field as a stand-in for "Name" to
        # detect and skip it.
        first_value = next(iter(fields.values()), "")
        if first_value in ("", "-"):
            continue

        holdings.append(Holding(status=status, fields=fields))
    return holdings


def parse_holdings(html: str, tabs: dict) -> list[Holding]:
    """Parse holdings across all tabs in `.si-portfolio-investments-tabs`.

    `tabs` maps a tab pane element id (e.g. "investments") to a status label
    (e.g. "current") used to tag each parsed holding.
    """
    soup = BeautifulSoup(html, "html.parser")
    holdings: list[Holding] = []
    for tab_id, status in tabs.items():
        pane = soup.select_one(f"#{tab_id}")
        if pane is None:
            continue
        table = pane.select_one("table.si-portfolio-table")
        if table is None:
            # Some pages may render the table as a direct sibling rather
            # than nested inside the tab pane; fall back to searching the
            # whole tab content block.
            continue
        holdings.extend(_parse_holdings_table(table, status))
    return holdings
