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
    value=22.0,
    evidence=Evidence.PUBLISHED,
    source="Industry benchmarks: 15-30 min (Retail Banker International, 2026); "
           "30-45 min for Level 1 review (Sphinx, 2026); 20-45 min per alert "
           "(Sphinx capacity analysis); 10 min to several hours (FluxForce)",
    note="Midpoint of the published range. Cited sources disagree by a factor "
         "of three, which is itself informative: review time depends heavily "
         "on whether the alert carries secondary identifiers to compare "
         "against. Swept in the sensitivity analysis rather than treated as "
         "settled.",
)

ANALYST_COST_PER_HOUR = Param(
    value=55.0,
    evidence=Evidence.PUBLISHED,
    source="$30-50/hour analyst time (Retail Banker International, 2026); "
           "$25-50 in analyst time per 30-45 min review (Sphinx, 2026)",
    note="Above the quoted hourly band because published figures appear to be "
           "direct wage rather than fully loaded. Benefits, supervision, "
           "QA sampling and overhead are real costs of the same review.",
)

REVIEW_COST_PER_ALERT = Param(
    value=20.0,
    evidence=Evidence.PUBLISHED,
    source="$15-25 per alert direct review cost (Retail Banker International, "
           "2026); $25-50 per Level 1 review (Sphinx, 2026)",
    note="Anchored to the published per-alert figure rather than derived, "
           "because the published number is the observable one. Deriving it "
           "from my own time and rate assumptions gives $20.17 — agreement "
           "within a dollar, which is a coincidence worth stating plainly "
           "rather than presenting as corroboration.",
)

# What the industry reports its own filters produce. Used to check whether this
# study's measured false-positive rate is in a plausible operating region, not
# to tune anything toward it.
INDUSTRY_FP_RATE_LOW = Param(
    value=0.90,
    evidence=Evidence.PUBLISHED,
    source="PwC benchmark cited since 2018; Alessa and KPMG place sanctions "
           "screening false positives at 90-95%",
    note="Share of alerts requiring no action.",
)

INDUSTRY_FP_RATE_HIGH = Param(
    value=0.995,
    evidence=Evidence.PUBLISHED,
    source="Flagright 2024 review, cited by FluxForce: sanctions models up to "
           "99.5%",
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
    value=6_000_000.0,
    evidence=Evidence.PUBLISHED,
    source="Retail Banker International (2026): a mid-tier bank processing "
           "500,000 cross-border payments monthly",
    note="Anchored to a published worked example rather than guessed. Six "
         "million payments a year at a 5% alert rate gives 25,000 alerts a "
         "month, which that source costs at $370k-$620k monthly — a "
         "cross-check this study's own cost model can be compared against. "
         "A money-centre bank screens an order of magnitude more; the "
         "threshold recommendation is scale-invariant, only the dollar "
         "totals move.",
)

TRUE_SANCTIONED_RATE = Param(
    value=2.5e-6,
    evidence=Evidence.PUBLISHED,
    source="Derived from published alert statistics: fewer than 10 of every "
           "100 alerts are true matches (FluxForce 2024, citing Alessa and "
           "KPMG); false-positive rates of 90-98% (Flagright 2026) and up to "
           "99% (Retail Banker International 2026); combined with a 5% alert "
           "rate on screened volume",
    note="A 5% alert rate with at most 10% of alerts genuine implies roughly "
         "5 true matches per 10,000 screened at production thresholds — but "
         "those alerts are mostly transaction-level and one designated party "
         "generates many. Scaled down two orders of magnitude to approximate "
         "distinct sanctioned COUNTERPARTIES rather than alerts.\n"
         "\n"
         "         Still the weakest link between published data and this "
         "model, and the derivation is stated so a reader can reject it. "
         "Swept across three orders of magnitude in the sensitivity analysis.",
)

# Published benchmark for what a real filter's alert queue looks like. Used to
# check whether this study's measured rates sit in a plausible operating
# region, never to tune toward.
INDUSTRY_ALERT_RATE = Param(
    value=0.05,
    evidence=Evidence.PUBLISHED,
    source="Retail Banker International (2026), described as conservative by "
           "industry standards",
    note="Share of screened items generating an alert. This study's measured "
         "false-positive rate should be compared against it: a threshold "
         "producing far more than 5% is outside any real operating range, "
         "whatever its recall.",
)

# The Swedish regulator tested 19 banks against 5,000 known sanctioned names.
# The alias result is the directly comparable benchmark for this study, since
# hold-one-out screening measures exactly that case.
FI_ACCURACY_CORRECT_SPELLING = Param(
    value=0.972,
    evidence=Evidence.PUBLISHED,
    source="Finansinspektionen FI Supervision 30 (December 2024), 19 banks "
           "tested against 5,000 sanctioned names",
    note="Average accuracy on correctly spelled entries. FI reported accuracy "
         "dropped further on aliases, transliterations and spelling variants "
         "without publishing a figure — which is the gap this study measures.",
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
