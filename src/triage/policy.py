"""
Tiered threshold policy.

No bank operates a single screening cut-off, and recommending one signals
unfamiliarity with how the function runs. Real policy has bands:

    auto-clear      below a floor, the hit is discarded without human review
    analyst review  between the floor and an escalation point, a first-line
                    analyst dispositions it
    escalate        above the escalation point, it goes to a senior reviewer
                    or straight to a payment block pending investigation

Why tiering dominates a single threshold
----------------------------------------
A single cut-off forces one decision to serve two purposes that pull in
opposite directions. Set it low enough to catch weak variants and the queue
becomes unworkable; set it high enough to keep the queue manageable and the
weak variants walk through.

Tiering separates them. The auto-clear floor governs COST, because everything
below it never reaches a human. The escalation point governs RISK, because
everything above it gets senior attention regardless of volume. The middle band
absorbs the ambiguity, and its width is a staffing decision rather than a
detection one.

That is also why the output of this project is a policy rather than a number.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .costs import CostAssumptions
from .evaluate import ThresholdPoint


@dataclass
class TierPolicy:
    auto_clear_below: float
    escalate_above: float

    recall_at_floor: float
    """Share of held-out variants still reachable — what the floor risks."""

    review_rate: float
    """Share of screened parties entering the analyst queue."""

    escalation_rate: float
    """Share reaching senior review."""

    alerts_per_10k: float
    escalations_per_10k: float

    annual_review_cost: float
    annual_escalation_cost: float
    exposure_cost: float
    total_cost: float
    analyst_fte: float

    missed_below_floor: float
    """Expected sanctioned parties per year discarded without any human
    seeing them. The number a regulator asks about first."""

    def as_dict(self) -> dict:
        return {
            "auto_clear_below": self.auto_clear_below,
            "escalate_above": self.escalate_above,
            "recall_at_floor": self.recall_at_floor,
            "review_rate": self.review_rate,
            "escalation_rate": self.escalation_rate,
            "alerts_per_10k_screened": self.alerts_per_10k,
            "escalations_per_10k_screened": self.escalations_per_10k,
            "annual_review_cost_usd": self.annual_review_cost,
            "annual_escalation_cost_usd": self.annual_escalation_cost,
            "exposure_cost_usd": self.exposure_cost,
            "total_cost_usd": self.total_cost,
            "analyst_fte": self.analyst_fte,
            "missed_below_floor_per_year": self.missed_below_floor,
        }


# Senior review costs more per item and is what an escalation buys.
ESCALATION_COST_MULTIPLE = 3.0


def evaluate_policy(points: list[ThresholdPoint],
                    auto_clear_below: float, escalate_above: float,
                    assumptions: CostAssumptions) -> TierPolicy | None:
    """
    Cost a two-boundary policy.

    The floor is the consequential boundary: anything below it is discarded
    with no human in the loop, so recall at the floor is the entire detection
    guarantee. The escalation point moves cost between first-line and senior
    review without changing what gets caught.
    """
    by_threshold = {p.threshold: p for p in points}
    floor = by_threshold.get(auto_clear_below)
    ceiling = by_threshold.get(escalate_above)
    if floor is None or ceiling is None:
        return None

    screenings = assumptions.screenings_per_year

    # Everything at or above the floor reaches a human.
    review_rate = floor.false_positive_rate
    escalation_rate = ceiling.false_positive_rate
    first_line_rate = max(0.0, review_rate - escalation_rate)

    first_line_alerts = first_line_rate * screenings
    escalated_alerts = escalation_rate * screenings

    review_cost = first_line_alerts * assumptions.review_cost_per_alert
    escalation_cost = (escalated_alerts * assumptions.review_cost_per_alert
                       * ESCALATION_COST_MULTIPLE)

    true_in_population = screenings * assumptions.true_sanctioned_rate
    missed = true_in_population * (1.0 - floor.recall)
    exposure = missed * assumptions.cost_per_miss

    from .costs import MINUTES_PER_ALERT
    minutes = float(MINUTES_PER_ALERT)
    fte = ((first_line_alerts * minutes
            + escalated_alerts * minutes * ESCALATION_COST_MULTIPLE)
           / 60.0 / 1800.0)

    return TierPolicy(
        auto_clear_below=auto_clear_below,
        escalate_above=escalate_above,
        recall_at_floor=floor.recall,
        review_rate=review_rate,
        escalation_rate=escalation_rate,
        alerts_per_10k=review_rate * 10_000,
        escalations_per_10k=escalation_rate * 10_000,
        annual_review_cost=review_cost,
        annual_escalation_cost=escalation_cost,
        exposure_cost=exposure,
        total_cost=review_cost + escalation_cost + exposure,
        analyst_fte=fte,
        missed_below_floor=missed,
    )


def search_policies(points: list[ThresholdPoint],
                    assumptions: CostAssumptions,
                    min_band: float = 6.0) -> list[TierPolicy]:
    """Cost every floor/escalation pair with a band of at least `min_band`."""
    out: list[TierPolicy] = []
    thresholds = [p.threshold for p in points]
    for floor in thresholds:
        for ceiling in thresholds:
            if ceiling - floor < min_band:
                continue
            policy = evaluate_policy(points, floor, ceiling, assumptions)
            if policy:
                out.append(policy)
    return out


@dataclass
class OperatingRange:
    """
    The band of defensible policies, rather than a single point.

    Produced because the cost-optimal threshold moved across the plausible
    range of nearly every assumption. When a recommendation is that sensitive
    to unvalidated inputs, quoting one number misrepresents the analysis. The
    honest output is the region where a policy survives every constraint, and
    a statement of what decides position inside it.
    """

    floor_low: float
    floor_high: float
    constraint_low: str
    constraint_high: str
    policies: list[TierPolicy] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "floor_low": self.floor_low,
            "floor_high": self.floor_high,
            "binding_constraint_at_low_end": self.constraint_low,
            "binding_constraint_at_high_end": self.constraint_high,
            "width": self.floor_high - self.floor_low,
            "policy_count": len(self.policies),
        }


def operating_range(points: list[ThresholdPoint],
                    assumptions: CostAssumptions,
                    *, max_fte: float = 150.0,
                    min_recall: float = 0.80) -> OperatingRange:
    """
    Floors that satisfy both a staffing ceiling and a recall floor.

    Two constraints, from opposite directions, and naming which one binds at
    each end is more useful than the midpoint:

      staffing   below some floor the queue exceeds any plausible headcount.
                 A policy nobody can staff is not a policy.
      recall     above some floor too many real variants are discarded with no
                 human review. A regulator does not accept an expected-value
                 argument for that.
    """
    viable: list[TierPolicy] = []
    for p in points:
        policy = evaluate_policy(points, p.threshold,
                                 min(100.0, p.threshold + 8), assumptions)
        if policy is None:
            continue
        if policy.analyst_fte <= max_fte and policy.recall_at_floor >= min_recall:
            viable.append(policy)

    if not viable:
        # Report the binding constraints rather than an empty answer: which
        # requirement is unsatisfiable is the finding.
        return OperatingRange(
            floor_low=0.0, floor_high=0.0,
            constraint_low=f"no floor keeps staffing under {max_fte:.0f} FTE",
            constraint_high=f"no floor reaches {min_recall:.0%} recall",
            policies=[],
        )

    floors = [p.auto_clear_below for p in viable]
    return OperatingRange(
        floor_low=min(floors), floor_high=max(floors),
        constraint_low=f"below this, the queue exceeds {max_fte:.0f} analyst FTE",
        constraint_high=f"above this, recall falls under {min_recall:.0%}",
        policies=viable,
    )
