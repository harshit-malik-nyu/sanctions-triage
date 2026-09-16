"""
The cost of being wrong, in each direction.

This is the part of the project that makes it a decision rather than a
measurement. A precision-recall curve says what happens at each threshold; it
does not say which threshold to pick. That requires knowing what each kind of
error costs, and those costs are wildly asymmetric here.

Every parameter carries an evidence class, because the difference between a
published enforcement figure and my estimate of an analyst's hourly cost is the
difference between a number you can defend and one you cannot:

    PUBLISHED   Sourced from OFAC's own enforcement data or another public
                record. Checkable.
    ESTIMATE    My assumption. Defensible, unverified, and the thing to attack.
    DERIVED     Computed from the above.

The single most important number in this module — the ratio between the cost of
a missed sanctioned party and the cost of a wasted review — is an ESTIMATE, and
the recommendation is deliberately reported across a wide range of it rather
than at one point. A reader who disagrees with my ratio can read their answer
off the sensitivity table instead of discarding the analysis.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class Evidence(str, Enum):
    PUBLISHED = "published"
    ESTIMATE = "estimate"
    DERIVED = "derived"


@dataclass(frozen=True)
class Param:
    value: Any
    evidence: Evidence
    source: str
    note: str = ""

    def __float__(self) -> float:
        return float(self.value)


# ---------------------------------------------------------------------------
# The cost of a false positive: analyst review
# ---------------------------------------------------------------------------

MINUTES_PER_ALERT = Param(
    value=12.0,
    evidence=Evidence.ESTIMATE,
    source="ESTIMATE — REQUIRES VALIDATION against an operations team",
    note="Time to clear one screening alert: open it, compare name, date of "
         "birth, nationality and identifiers against the list entry, record a "
         "disposition. Straightforward hits go faster; anything needing "
         "escalation goes far slower.",
)

ANALYST_COST_PER_HOUR = Param(
    value=85.0,
    evidence=Evidence.ESTIMATE,
    source="ESTIMATE — fully loaded cost, REQUIRES VALIDATION",
    note="Salary, benefits, supervision and overhead for a first-line "
         "sanctions analyst in a US money-centre bank. Offshored review is "
         "materially cheaper and would lower this substantially.",
)

REVIEW_COST_PER_ALERT = Param(
    value=float(MINUTES_PER_ALERT) / 60.0 * float(ANALYST_COST_PER_HOUR),
    evidence=Evidence.DERIVED,
    source="MINUTES_PER_ALERT x ANALYST_COST_PER_HOUR",
)


# ---------------------------------------------------------------------------
# The cost of a false negative: a missed sanctioned party
# ---------------------------------------------------------------------------
# This side is grounded in OFAC's own published enforcement record rather than
# in assumption, which is the main reason this project uses OFAC rather than a
# generic anomaly-detection dataset.

IEEPA_STATUTORY_MAX = Param(
    value=377_700.0,
    evidence=Evidence.PUBLISHED,
    source="IEEPA civil penalty maximum per violation, inflation-adjusted; "
           "OFAC penalty schedule",
    note="Per violation, not per case. OFAC aggregates across transactions, "
         "which is how settlements reach the hundreds of millions.",
)

PENALTY_DISTRIBUTION_NOTE = Param(
    value="see evidence/penalties/",
    evidence=Evidence.PUBLISHED,
    source="OFAC Civil Penalties and Enforcement Information, 2003-present",
    note="OFAC publishes every civil penalty and settlement by year with the "
         "counterparty named and the amount in dollars. The study parses that "
         "record rather than assuming a distribution, so the loss side is "
         "anchored to what OFAC has actually collected.",
)

PROBABILITY_MISS_BECOMES_ENFORCEMENT = Param(
    value=0.02,
    evidence=Evidence.ESTIMATE,
    source="ESTIMATE — the weakest number in this model",
    note="Share of missed sanctioned parties that become a public enforcement "
         "action. Unknowable from public data by construction: a miss that was "
         "never detected leaves no record to count. Swept across two orders of "
         "magnitude in the sensitivity analysis rather than defended.",
)

REMEDIATION_MULTIPLE = Param(
    value=2.5,
    evidence=Evidence.ESTIMATE,
    source="ESTIMATE — REQUIRES VALIDATION",
    note="Total cost as a multiple of the headline penalty: lookback reviews, "
         "consent-order monitoring, legal fees, systems remediation. The "
         "penalty is the visible part, not the whole.",
)


# ---------------------------------------------------------------------------
# Operating volume
# ---------------------------------------------------------------------------

SCREENINGS_PER_YEAR = Param(
    value=50_000_000.0,
    evidence=Evidence.ESTIMATE,
    source="ESTIMATE — order of magnitude for a large US bank",
    note="Customer and transaction screening events per year. Used only to "
         "convert per-10,000 rates into an annual figure; the threshold "
         "recommendation itself is scale-invariant.",
)

TRUE_SANCTIONED_RATE = Param(
    value=1e-6,
    evidence=Evidence.ESTIMATE,
    source="ESTIMATE — REQUIRES VALIDATION",
    note="Share of screened parties genuinely on a sanctions list. Extremely "
         "low, which is exactly why precision is so poor at any usable recall: "
         "with a base rate this small, even a very specific filter produces "
         "mostly false positives. This is the arithmetic behind the industry's "
         "alert-fatigue problem and it is not a tuning failure.",
)


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

@dataclass
class CostAssumptions:
    """Mutable copy of the parameters, so sensitivity runs cannot leak state."""

    review_cost_per_alert: float = float(REVIEW_COST_PER_ALERT)
    penalty_per_enforcement: float = float(IEEPA_STATUTORY_MAX)
    p_miss_becomes_enforcement: float = float(PROBABILITY_MISS_BECOMES_ENFORCEMENT)
    remediation_multiple: float = float(REMEDIATION_MULTIPLE)
    screenings_per_year: float = float(SCREENINGS_PER_YEAR)
    true_sanctioned_rate: float = float(TRUE_SANCTIONED_RATE)

    @property
    def cost_per_miss(self) -> float:
        """Expected cost of letting one sanctioned party through."""
        return (self.penalty_per_enforcement
                * self.p_miss_becomes_enforcement
                * self.remediation_multiple)

    @property
    def asymmetry_ratio(self) -> float:
        """
        How many wasted reviews one miss is worth.

        The whole decision turns on this. Reporting it explicitly means a
        reader who thinks it is wrong can say so precisely rather than
        rejecting the analysis wholesale.
        """
        return self.cost_per_miss / self.review_cost_per_alert


def expected_annual_cost(
    *,
    alerts_per_screening: float,
    recall: float,
    assumptions: CostAssumptions,
) -> dict[str, float]:
    """
    Annual cost of operating at one threshold.

    Two terms:

      review    every alert costs analyst time, whether or not it is real
      exposure  every sanctioned party the filter misses carries an expected
                enforcement cost

    Deliberately NOT included: the cost of a blocked legitimate payment, of
    customer attrition from over-blocking, or of reputational damage. All are
    real; none is estimable from public data, and inventing them would put
    invented numbers in the decision rather than in the acknowledged gaps.
    """
    screenings = assumptions.screenings_per_year

    alerts = alerts_per_screening * screenings
    review_cost = alerts * assumptions.review_cost_per_alert

    true_positives_in_population = screenings * assumptions.true_sanctioned_rate
    missed = true_positives_in_population * (1.0 - recall)
    exposure = missed * assumptions.cost_per_miss

    return {
        "alerts_per_year": alerts,
        "review_cost": review_cost,
        "expected_missed": missed,
        "exposure_cost": exposure,
        "total_cost": review_cost + exposure,
        "analyst_fte": alerts * float(MINUTES_PER_ALERT) / 60.0 / 1800.0,
    }


def registry() -> dict[str, Param]:
    return {k: v for k, v in globals().items() if isinstance(v, Param)}


def audit() -> str:
    """Human-readable parameter register, printed by `make audit`."""
    lines = ["COST MODEL PARAMETERS", "=" * 78, ""]
    for cls in (Evidence.PUBLISHED, Evidence.DERIVED, Evidence.ESTIMATE):
        group = {k: v for k, v in registry().items() if v.evidence == cls}
        if not group:
            continue
        lines.append(f"[{cls.value.upper()}]  {len(group)} parameters")
        lines.append("-" * 78)
        for name, p in sorted(group.items()):
            lines.append(f"  {name}")
            lines.append(f"    value  : {p.value}")
            lines.append(f"    source : {p.source}")
            if p.note:
                lines.append(f"    note   : {p.note}")
            lines.append("")
        lines.append("")

    a = CostAssumptions()
    lines.append("=" * 78)
    lines.append(f"  review cost per alert : ${a.review_cost_per_alert:,.2f}")
    lines.append(f"  expected cost per miss: ${a.cost_per_miss:,.2f}")
    lines.append(f"  asymmetry ratio       : {a.asymmetry_ratio:,.0f} reviews "
                 "are worth one miss")
    lines.append("")
    lines.append("  The asymmetry ratio is the decision. It rests on an")
    lines.append("  ESTIMATE that cannot be validated from public data, so the")
    lines.append("  recommendation is reported across a range of it.")
    return "\n".join(lines)


if __name__ == "__main__":
    print(audit())
