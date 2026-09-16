"""
Threshold evaluation.

Two measurements, each with ground truth established by construction rather
than by labelling.

    RECALL          Hold-one-out screening of real OFAC aliases.

                    The first version of this got the experiment wrong, and
                    the error is instructive. It screened aliases against a
                    watchlist built from PRIMARY NAMES ONLY, which no bank
                    runs: a real filter loads every published name, primary
                    and alias alike. That made acronym aliases — `COIBA`,
                    `ALEPH`, `BATASUNA` — impossible to match by construction,
                    and produced a 37.9% recall ceiling that was an artefact of
                    the setup rather than a property of screening.

                    The watchlist now contains primary names AND aliases, with
                    the specific alias under test removed. That is the question
                    worth asking: when a sanctioned party presents a name
                    variant the list has not seen, does the filter still reach
                    the right entity through the variants it has?

    FALSE POSITIVES Screen real registered companies against the same
                    watchlist. Any alert is a false positive, because those
                    companies are not sanctioned — verified by exact-match
                    removal before the sweep begins.

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
class WatchlistName:
    """
    One screenable name on the watchlist.

    A real sanctions filter indexes every published name for an entity, not
    just the primary one, so the unit here is a NAME rather than an entry.
    """

    name: str
    ent_num: int
    is_primary: bool


@dataclass
class AliasResult:
    """One held-out alias screened against the remaining watchlist."""

    alias: str
    true_ent_num: int
    matched_ent_num: int | None
    matched_name: str | None
    score: float
    correct: bool
    """Top match belongs to the correct entity."""

    alerted_on_sanctioned: bool = False
    """
    Top match is some sanctioned entity, though not the right one.

    Worth separating. Two SDN entries frequently describe the same real
    organisation — `AL-AQSA FOUNDATION` is listed several times by country —
    and an analyst who sees a hit on either blocks the payment. Counting that
    as a miss understates what the filter achieves operationally, while
    counting it as a clean catch would overstate precision of attribution.
    Both numbers are reported.
    """


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


def build_watchlist(entries, aliases) -> list[WatchlistName]:
    """
    Every published name, primary and alias, as a real filter would load it.
    """
    out = [WatchlistName(e.name, e.ent_num, True) for e in entries]
    keep = {e.ent_num for e in entries}
    out.extend(WatchlistName(a.name, a.ent_num, False)
               for a in aliases if a.ent_num in keep)
    return out


def screen_aliases(aliases, watchlist: list[WatchlistName],
                   index=None, limit=None, clustering=None) -> list[AliasResult]:
    """
    Hold-one-out screening.

    For each alias, the identical string is excluded from the watchlist before
    matching. Without that exclusion the alias matches itself at 100 and the
    measurement is circular — it would report near-perfect recall while
    testing nothing.

    Exclusion is by normalised string rather than by index position, because
    the same name can appear under several entity numbers and leaving a
    duplicate in would readmit the trivial self-match.
    """
    names = [w.name for w in watchlist]
    index = index if index is not None else candidate_index(names)

    out: list[AliasResult] = []
    for i, (alias, _target) in enumerate(aliases):
        if limit and i >= limit:
            break

        held_out = normalise(alias.name)
        best_pos, best_score = -1, 0.0

        from .match import candidates_for, score as name_score
        for pos in candidates_for(alias.name, index):
            if normalise(names[pos]) == held_out:
                continue          # the held-out variant, and its duplicates
            s = name_score(alias.name, names[pos])
            if s > best_score:
                best_pos, best_score = pos, s

        matched = watchlist[best_pos].ent_num if best_pos >= 0 else None

        # A catch is a hit on the right ORGANISATION, not the right listing.
        # OFAC designates the same group under several entity numbers, and
        # requiring exact equality counted a perfect match against a sister
        # listing as a miss.
        if clustering is not None:
            hit = clustering.same_org(matched, alias.ent_num)
        else:
            hit = (matched == alias.ent_num)

        out.append(AliasResult(
            alias=alias.name,
            true_ent_num=alias.ent_num,
            matched_ent_num=matched,
            matched_name=names[best_pos] if best_pos >= 0 else None,
            score=best_score,
            correct=hit,
            alerted_on_sanctioned=(matched is not None and not hit),
        ))
        if (i + 1) % 2000 == 0:
            log.info("screened %s aliases", i + 1)
    return out


def screen_clean(entities, watchlist: list[WatchlistName],
                 index=None, limit=None) -> list[CleanResult]:
    names = [w.name for w in watchlist]
    ent_nums = [w.ent_num for w in watchlist]
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
    aliases_operational: int     # alerted on any sanctioned entity
    recall: float
    operational_recall: float
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
            "operational_recall": self.operational_recall,
            "recall_ci95": list(self.recall_ci),
            "aliases_caught": self.aliases_caught,
            "aliases_operational": self.aliases_operational,
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

        # Operational catch: the filter alerted on SOME sanctioned entity, so
        # an analyst reviews and blocks even if the attribution is to a sister
        # listing of the same organisation.
        operational = sum(1 for r in alerted
                          if r.correct or r.alerted_on_sanctioned)

        fp = sum(1 for r in clean_results if r.score >= t)
        fpr = fp / n_clean if n_clean else 0.0

        points.append(ThresholdPoint(
            threshold=t,
            aliases_total=n_alias,
            aliases_alerted=len(alerted),
            aliases_caught=caught,
            aliases_operational=operational,
            operational_recall=operational / n_alias if n_alias else 0.0,
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
