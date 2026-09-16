"""
The decision.

A precision-recall curve describes what happens at each threshold. It does not
say which one to choose. That requires the cost of each error, and here those
costs differ by three orders of magnitude, so the choice is driven almost
entirely by an assumption rather than by the data.

This module makes that visible instead of hiding it. It computes the
cost-minimising threshold, then re-computes it across the plausible range of
the assumption it depends on most, and reports how far the answer moves. Where
the recommendation is stable across that range it can be stated plainly; where
it is not, the honest output is the range rather than a point.

Why not maximise F1
-------------------
F1 treats a false positive and a false negative as equally costly. In sanctions
screening they differ by roughly a thousand to one, and the direction is not
symmetric: a wasted review costs an analyst twenty minutes, a missed
designation costs a consent order. Reporting an F1-optimal threshold here would
be optimising a quantity nobody in a compliance function uses, and would land
far from any defensible operating point.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .costs import CostAssumptions
from .evaluate import ThresholdPoint


@dataclass
class Option:
    """One threshold, costed."""

    threshold: float
    recall: float
    recall_ci: tuple[float, float]
    false_positive_rate: float
    alerts_per_10k: float

    alerts_per_year: float
    review_cost: float
    expected_missed: float
    exposure_cost: float
    total_cost: float
    analyst_fte: float

    def as_dict(self) -> dict:
        return {
            "threshold": self.threshold,
            "recall": self.recall,
            "recall_ci95": list(self.recall_ci),
            "false_positive_rate": self.false_positive_rate,
            "alerts_per_10k_screened": self.alerts_per_10k,
            "alerts_per_year": self.alerts_per_year,
            "review_cost_usd": self.review_cost,
            "expected_missed_per_year": self.expected_missed,
            "exposure_cost_usd": self.exposure_cost,
            "total_cost_usd": self.total_cost,
            "analyst_fte": self.analyst_fte,
        }


def cost_options(points: list[ThresholdPoint],
                 assumptions: CostAssumptions) -> list[Option]:
    from .costs import MINUTES_PER_ALERT

    out: list[Option] = []
    for p in points:
        screenings = assumptions.screenings_per_year
        alerts = p.false_positive_rate * screenings
        review = alerts * assumptions.review_cost_per_alert

        true_in_population = screenings * assumptions.true_sanctioned_rate
        missed = true_in_population * (1.0 - p.recall)
        exposure = missed * assumptions.cost_per_miss

        out.append(Option(
            threshold=p.threshold,
            recall=p.recall,
            recall_ci=p.recall_ci,
            false_positive_rate=p.false_positive_rate,
            alerts_per_10k=p.alerts_per_10k,
            alerts_per_year=alerts,
            review_cost=review,
            expected_missed=missed,
            exposure_cost=exposure,
            total_cost=review + exposure,
            analyst_fte=alerts * float(MINUTES_PER_ALERT) / 60.0 / 1800.0,
        ))
    return out


def optimal(options: list[Option]) -> Option | None:
    """Lowest total expected cost."""
    return min(options, key=lambda o: o.total_cost) if options else None


def minimum_acceptable_recall(options: list[Option],
                              floor: float = 0.95) -> Option | None:
    """
    Cheapest threshold meeting a recall floor.

    Offered alongside the cost optimum because a real compliance function does
    not get to choose purely on expected cost. A regulator does not accept
    "we tuned it out because the expected value worked" as an answer for a
    missed designation, and a recall floor is closer to how these decisions are
    actually constrained.
    """
    eligible = [o for o in options if o.recall >= floor]
    return min(eligible, key=lambda o: o.total_cost) if eligible else None


@dataclass
class Sensitivity:
    parameter: str
    values: list[float] = field(default_factory=list)
    optimal_thresholds: list[float] = field(default_factory=list)
    recalls: list[float] = field(default_factory=list)

    @property
    def threshold_range(self) -> tuple[float, float]:
        return (min(self.optimal_thresholds), max(self.optimal_thresholds)) \
            if self.optimal_thresholds else (0.0, 0.0)

    @property
    def is_stable(self) -> bool:
        """
        Whether the recommendation survives the assumption moving.

        Six points is the width of one step in the threshold sweep either way.
        A recommendation that moves further than that across a plausible range
        of an unvalidated input is not a recommendation; it is a restatement of
        the assumption.
        """
        lo, hi = self.threshold_range
        return (hi - lo) <= 6.0

    def as_dict(self) -> dict:
        return {
            "parameter": self.parameter,
            "values": self.values,
            "optimal_thresholds": self.optimal_thresholds,
            "recalls_at_optimum": self.recalls,
            "threshold_range": list(self.threshold_range),
            "stable": self.is_stable,
        }


def sweep_assumption(points: list[ThresholdPoint], parameter: str,
                     values: list[float],
                     base: CostAssumptions | None = None) -> Sensitivity:
    """Re-derive the optimum with one assumption varied."""
    base = base or CostAssumptions()
    result = Sensitivity(parameter=parameter, values=list(values))

    for v in values:
        trial = CostAssumptions(**{**base.__dict__, parameter: v})
        best = optimal(cost_options(points, trial))
        if best:
            result.optimal_thresholds.append(best.threshold)
            result.recalls.append(best.recall)

    return result


def full_sensitivity(points: list[ThresholdPoint],
                     base: CostAssumptions | None = None) -> list[Sensitivity]:
    """
    Vary every contested input across a defensible range.

    The ranges are wide on purpose. A conclusion that only holds for one set of
    numbers I chose is not a conclusion, and the reader most worth convincing
    is the one who thinks my numbers are wrong.
    """
    base = base or CostAssumptions()
    return [
        sweep_assumption(points, "p_miss_becomes_enforcement",
                         [0.002, 0.01, 0.02, 0.05, 0.20], base),
        sweep_assumption(points, "penalty_per_enforcement",
                         [50_000, 377_700, 1_000_000, 10_000_000, 100_000_000],
                         base),
        sweep_assumption(points, "review_cost_per_alert",
                         [4.0, 8.0, 17.0, 34.0, 60.0], base),
        sweep_assumption(points, "true_sanctioned_rate",
                         [1e-7, 5e-7, 1e-6, 1e-5, 1e-4], base),
        sweep_assumption(points, "remediation_multiple",
                         [1.0, 2.5, 5.0, 10.0], base),
    ]


@dataclass
class Recommendation:
    cost_optimal: Option | None
    recall_constrained: Option | None
    recall_floor: float
    sensitivities: list[Sensitivity] = field(default_factory=list)
    separation: dict = field(default_factory=dict)

    @property
    def stable_parameters(self) -> list[str]:
        return [s.parameter for s in self.sensitivities if s.is_stable]

    @property
    def unstable_parameters(self) -> list[str]:
        return [s.parameter for s in self.sensitivities if not s.is_stable]

    def as_dict(self) -> dict:
        return {
            "cost_optimal": self.cost_optimal.as_dict() if self.cost_optimal else None,
            "recall_constrained": (self.recall_constrained.as_dict()
                                   if self.recall_constrained else None),
            "recall_floor": self.recall_floor,
            "sensitivities": [s.as_dict() for s in self.sensitivities],
            "stable_under": self.stable_parameters,
            "unstable_under": self.unstable_parameters,
            "separation": self.separation,
        }


def recommend(points: list[ThresholdPoint],
              *, assumptions: CostAssumptions | None = None,
              recall_floor: float = 0.95,
              separation: dict | None = None) -> Recommendation:
    assumptions = assumptions or CostAssumptions()
    options = cost_options(points, assumptions)
    return Recommendation(
        cost_optimal=optimal(options),
        recall_constrained=minimum_acceptable_recall(options, recall_floor),
        recall_floor=recall_floor,
        sensitivities=full_sensitivity(points, assumptions),
        separation=separation or {},
    )
