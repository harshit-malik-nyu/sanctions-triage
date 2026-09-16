"""
Threshold evaluation.

Two measurements, each with ground truth established by construction rather
than by labelling:

    RECALL          Screen real OFAC aliases against the primary-name
                    watchlist. Each alias carries the entity number it belongs
                    to, so a correct catch is unambiguous: the top match must
                    be that entity. An alias that fails to match is a real
                    sanctioned party a real filter would let through.

    FALSE POSITIVES Screen real registered companies against the same
                    watchlist. Any alert is a false positive, because those
                    companies are not sanctioned — verified by exact-match
                    removal before the sweep begins.

Precision is deliberately not the headline. With a true-sanctioned base rate
near one in a million, precision at any usable recall is close to zero, and
quoting it invites the reader to conclude the filter is broken. It is not
broken; the arithmetic of screening a clean population against a watchlist
simply produces mostly false positives, and the operationally meaningful
quantity is alerts per ten thousand screened.

That framing difference is the difference between a metric and a decision.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

from .match import best_match, candidate_index, normalise

log = logging.getLogger(__name__)


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """
    Wilson score interval.

    Used rather than the normal approximation because recall here sits near
    1.0, where the textbook interval produces an upper bound above one and
    understates uncertainty.
    """
    if n == 0:
        return (0.0, 0.0)
    p = successes / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return (max(0.0, centre - margin), min(1.0, centre + margin))


@dataclass
class AliasResult:
    """One real alias screened against the watchlist."""

    alias: str
    true_ent_num: int
    matched_ent_num: int | None
    score: float
    correct: bool


@dataclass
class CleanResult:
    """One real company screened against the watchlist."""

    name: str
    identifier: str
    top_match: str | None
    top_ent_num: int | None
    score: float


@dataclass
class ScreeningRun:
    alias_results: list[AliasResult] = field(default_factory=list)
    clean_results: list[CleanResult] = field(default_factory=list)
    watchlist_size: int = 0
    comparisons: int = 0


def screen_aliases(aliases, watchlist, index=None, limit=None) -> list[AliasResult]:
    """
    Score every alias against the watchlist, recording the best hit.

    Scoring is done once, at full resolution. The threshold sweep then reads
    off these scores rather than re-screening, which is both far faster and
    guarantees every threshold sees identical underlying comparisons.
    """
    names = [e.name for e in watchlist]
    ent_nums = [e.ent_num for e in watchlist]
    index = index if index is not None else candidate_index(names)

    out: list[AliasResult] = []
    for i, (alias, target) in enumerate(aliases):
        if limit and i >= limit:
            break
        pos, sc = best_match(alias.name, names, index)
        matched = ent_nums[pos] if pos >= 0 else None
        out.append(AliasResult(
            alias=alias.name,
            true_ent_num=alias.ent_num,
            matched_ent_num=matched,
            score=sc,
            correct=(matched == alias.ent_num),
        ))
        if (i + 1) % 2000 == 0:
            log.info("screened %s aliases", i + 1)
    return out


def screen_clean(entities, watchlist, index=None, limit=None) -> list[CleanResult]:
    names = [e.name for e in watchlist]
    ent_nums = [e.ent_num for e in watchlist]
    index = index if index is not None else candidate_index(names)

    out: list[CleanResult] = []
    for i, ent in enumerate(entities):
        if limit and i >= limit:
            break
        pos, sc = best_match(ent.name, names, index)
        out.append(CleanResult(
            name=ent.name,
            identifier=ent.identifier,
            top_match=names[pos] if pos >= 0 else None,
            top_ent_num=ent_nums[pos] if pos >= 0 else None,
            score=sc,
        ))
        if (i + 1) % 2000 == 0:
            log.info("screened %s clean entities", i + 1)
    return out


@dataclass
class ThresholdPoint:
    threshold: float

    aliases_total: int
    aliases_alerted: int
    aliases_caught: int          # alerted AND matched to the right entity
    recall: float
    recall_ci: tuple[float, float]

    clean_total: int
    clean_alerted: int
    false_positive_rate: float
    fpr_ci: tuple[float, float]
    alerts_per_10k: float

    def as_dict(self) -> dict:
        return {
            "threshold": self.threshold,
            "recall": self.recall,
            "recall_ci95": list(self.recall_ci),
            "aliases_caught": self.aliases_caught,
            "aliases_total": self.aliases_total,
            "false_positive_rate": self.false_positive_rate,
            "fpr_ci95": list(self.fpr_ci),
            "alerts_per_10k_screened": self.alerts_per_10k,
            "clean_alerted": self.clean_alerted,
            "clean_total": self.clean_total,
        }


def sweep(alias_results: list[AliasResult],
          clean_results: list[CleanResult],
          thresholds: list[float] | None = None) -> list[ThresholdPoint]:
    """
    Recall and false-positive rate at each threshold.

    A catch requires BOTH that the alias alerted and that the top match was the
    correct entity. Alerting on the wrong sanctioned party is not a catch: the
    analyst investigates the wrong entry, finds it does not match, and clears
    the alert — the real party goes through. Counting that as recall would
    overstate performance in exactly the way that matters.
    """
    thresholds = thresholds or [float(t) for t in range(50, 101, 2)]
    points: list[ThresholdPoint] = []

    n_alias = len(alias_results)
    n_clean = len(clean_results)

    for t in thresholds:
        alerted = [r for r in alias_results if r.score >= t]
        caught = sum(1 for r in alerted if r.correct)
        recall = caught / n_alias if n_alias else 0.0

        fp = sum(1 for r in clean_results if r.score >= t)
        fpr = fp / n_clean if n_clean else 0.0

        points.append(ThresholdPoint(
            threshold=t,
            aliases_total=n_alias,
            aliases_alerted=len(alerted),
            aliases_caught=caught,
            recall=recall,
            recall_ci=wilson_interval(caught, n_alias),
            clean_total=n_clean,
            clean_alerted=fp,
            false_positive_rate=fpr,
            fpr_ci=wilson_interval(fp, n_clean),
            alerts_per_10k=fpr * 10_000,
        ))

    return points


def separation(alias_results: list[AliasResult],
               clean_results: list[CleanResult]) -> dict:
    """
    How far apart the two score distributions actually are.

    Reported because it bounds what any threshold can achieve. Where the
    distributions overlap heavily, no threshold separates them and the choice
    is purely about which error to accept — which is the honest framing, and
    the opposite of what a single recommended number implies.
    """
    correct = sorted(r.score for r in alias_results if r.correct)
    clean = sorted(r.score for r in clean_results)
    if not correct or not clean:
        return {}

    def pct(xs, q):
        return xs[min(len(xs) - 1, int(len(xs) * q))]

    overlap_lo = pct(correct, 0.05)
    overlap_hi = pct(clean, 0.95)

    return {
        "alias_p05": overlap_lo,
        "alias_median": pct(correct, 0.5),
        "clean_median": pct(clean, 0.5),
        "clean_p95": overlap_hi,
        "clean_max": clean[-1],
        "distributions_overlap": overlap_lo <= overlap_hi,
        "overlap_band": [min(overlap_lo, overlap_hi), max(overlap_lo, overlap_hi)],
        "note": (
            "Where the 5th percentile of correctly-matched aliases sits below "
            "the 95th percentile of clean companies, no threshold separates "
            "the classes and the decision is purely which error to absorb."
        ),
    }
