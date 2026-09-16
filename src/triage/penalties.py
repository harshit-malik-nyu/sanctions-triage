"""
OFAC's published enforcement record.

The cost of a missed sanctioned party is the single hardest number in this
analysis, and it is where most treatments of this problem either hand-wave or
quote the statutory maximum as though every violation drew it.

OFAC publishes better than that. Every civil penalty and settlement since 2003
appears on its site by year, with the counterparty named and the amount in
dollars. Parsing that record replaces an assumption with a distribution: not
"a violation costs the statutory maximum" but "here is what OFAC has actually
collected, and here is its shape".

What this does and does not establish
-------------------------------------
It establishes what a *detected and prosecuted* violation has cost. It does
not establish what a *missed* one costs, because the two differ by a factor
nobody can observe: the share of misses that ever surface. That factor is an
explicit estimate in `costs.py`, swept across two orders of magnitude, and it
is named there as the weakest number in the model.

The distinction matters. Anchoring to real penalties makes the loss side
defensible; pretending the anchor is complete would not.
"""

from __future__ import annotations

import html
import logging
import re
import statistics
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone

log = logging.getLogger(__name__)

BASE = ("https://ofac.treasury.gov/civil-penalties-and-enforcement-information/"
        "{year}-enforcement-information")
USER_AGENT = ("sanctions-triage-research/0.1 "
              "(non-commercial research; contact via GitHub issues)")

# Rows look like: date | name | count | amount. The amount carries commas and
# sometimes a decimal; "N/A" appears for findings of violation with no penalty.
_TAG = re.compile(r"<[^>]+>")
_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
_CELL = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S | re.I)
_AMOUNT = re.compile(r"^\$?\s*([\d,]+(?:\.\d+)?)\s*$")
_DATE = re.compile(r"^\s*(\d{1,2})/(\d{1,2})/(\d{4})")


@dataclass
class Penalty:
    year: int
    date: str | None
    counterparty: str
    count: int
    amount_usd: float | None

    @property
    def has_amount(self) -> bool:
        return self.amount_usd is not None and self.amount_usd > 0


@dataclass
class PenaltyRecord:
    penalties: list[Penalty] = field(default_factory=list)
    years_fetched: list[int] = field(default_factory=list)
    years_failed: list[int] = field(default_factory=list)
    retrieved_utc: str = ""

    def with_amounts(self) -> list[Penalty]:
        return [p for p in self.penalties if p.has_amount]

    def amounts(self) -> list[float]:
        return sorted(p.amount_usd for p in self.with_amounts())  # type: ignore[misc]

    def summary(self) -> dict:
        amts = self.amounts()
        if not amts:
            return {"count": 0, "note": "no penalty amounts parsed"}

        return {
            "count": len(amts),
            "years": f"{min(self.years_fetched)}-{max(self.years_fetched)}"
                     if self.years_fetched else "",
            "years_failed": self.years_failed,
            "total_usd": sum(amts),
            "mean_usd": statistics.mean(amts),
            "median_usd": statistics.median(amts),
            "p25_usd": amts[len(amts) // 4],
            "p75_usd": amts[3 * len(amts) // 4],
            "p90_usd": amts[int(len(amts) * 0.9)],
            "max_usd": max(amts),
            "min_usd": min(amts),
            "note": (
                "Median and mean differ by orders of magnitude because the "
                "distribution is dominated by a handful of very large "
                "institutional settlements. The median is the better anchor "
                "for a typical violation; the tail is what makes the "
                "expected value large."
            ),
        }


def _text(fragment: str) -> str:
    return html.unescape(_TAG.sub(" ", fragment)).strip()


def parse_year(page: str, year: int) -> list[Penalty]:
    """Extract penalty rows from one year's published chart."""
    out: list[Penalty] = []

    for row_html in _ROW.findall(page):
        cells = [_text(c) for c in _CELL.findall(row_html)]
        cells = [c for c in cells if c not in ("", "&nbsp;")]
        if len(cells) < 3:
            continue

        date_m = _DATE.match(cells[0])
        if not date_m:
            continue          # header or a layout row

        # Trailing cells: amount is last, count is usually the one before.
        amount: float | None = None
        for cell in reversed(cells):
            m = _AMOUNT.match(cell.replace("$", "").strip())
            if m:
                try:
                    amount = float(m.group(1).replace(",", ""))
                except ValueError:
                    amount = None
                break

        count = 1
        for cell in reversed(cells[1:]):
            stripped = cell.replace(",", "").strip()
            if stripped.isdigit() and len(stripped) <= 3:
                count = int(stripped)
                break

        name = cells[1].strip() if len(cells) > 1 else ""
        if not name:
            continue

        # A count captured as the amount happens when the amount cell is N/A.
        if amount is not None and amount == count and amount < 100:
            amount = None

        out.append(Penalty(
            year=year, date=cells[0].strip(), counterparty=name,
            count=count, amount_usd=amount,
        ))

    return out


def fetch(years: list[int], timeout: int = 60) -> PenaltyRecord:
    """Retrieve and parse OFAC's enforcement chart for each year."""
    record = PenaltyRecord(
        retrieved_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"))

    for year in years:
        url = BASE.format(year=year)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                page = resp.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
            log.warning("penalties %s unavailable: %s", year, exc)
            record.years_failed.append(year)
            continue

        rows = parse_year(page, year)
        if not rows:
            log.warning("penalties %s: page fetched but no rows parsed — the "
                        "table layout may have changed", year)
            record.years_failed.append(year)
            continue

        record.penalties.extend(rows)
        record.years_fetched.append(year)
        log.info("penalties %s: %s actions, %s with amounts",
                 year, len(rows), sum(1 for r in rows if r.has_amount))

    return record


def loss_anchors(record: PenaltyRecord) -> dict[str, float]:
    """
    Candidate anchors for the cost of one enforcement action.

    Three are offered rather than one, because the choice is a judgment and
    hiding it inside a single number would misrepresent how much the answer
    depends on it:

      median      a typical action. Understates exposure for a large bank,
                  whose violations are more likely to be systemic.
      mean        pulled far above the median by institutional settlements.
                  Arguably the right expected value, but unstable — one
                  billion-dollar case moves it.
      p90         a bad but not catastrophic outcome. The most defensible
                  single figure for a money-centre bank in my view, and the
                  one the headline uses.
    """
    amts = record.amounts()
    if not amts:
        return {}
    return {
        "median": statistics.median(amts),
        "mean": statistics.mean(amts),
        "p90": amts[int(len(amts) * 0.9)],
    }
