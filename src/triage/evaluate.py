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
    """
    One held-out alias screened against the remaining watchlist.

    `hit_score` is the crucial field, and getting to it required correcting a
    modelling error. The first version recorded only the single best match, so
    an alias whose true organisation ranked second was scored as a miss. No
    screening filter works that way: it returns every entry above threshold
    and an analyst works the list. If the correct organisation appears
    anywhere in that list, the party is caught.

    `hit_score` is therefore the highest score achieved against the TRUE
    organisation, and recall at a threshold is the share of aliases whose
    hit_score clears it. `top_score` is retained separately because the gap
    between them is itself operationally meaningful: it is how far down the
    alert list an analyst has to read.
    """

    alias: str
    true_ent_num: int

    hit_score: float
    """Best score against any name belonging to the true organisation."""

    top_score: float
    """Best score against anything on the watchlist."""

    top_ent_num: int | None
    top_name: str | None

    rank_of_true: int | None = None
    """
    Position of the true organisation in the alert list, 1-based.

    None when it never scores above the floor. A rank of 1 means the filter
    put the right answer first; a rank of 40 means it is technically caught
    and practically buried.
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
    Hold-one-out screening, scored as a filter actually behaves.

    Two corrections are baked in here, both found by reading results rather
    than rates.

    The alias under test is excluded from the watchlist by normalised string.
    Without that the alias matches itself at 100 and the measurement is
    circular — near-perfect recall, nothing tested. Exclusion is by string
    rather than index because the same name appears under several entity
    numbers and a duplicate readmits the self-match.

    Every candidate is scored, not just the best. A screening filter returns
    all entries above threshold and an analyst works the list, so the question
    is whether the true organisation appears ANYWHERE in it — not whether it
    ranked first. Recording only the top hit understated recall by counting a
    correct second-place answer as a miss.
    """
    from .match import candidates_for, score as name_score

    names = [w.name for w in watchlist]
    ents = [w.ent_num for w in watchlist]
    index = index if index is not None else candidate_index(names)

    def same_org(a, b):
        if clustering is not None:
            return clustering.same_org(a, b)
        return a == b

    out: list[AliasResult] = []
    for i, (alias, _target) in enumerate(aliases):
        if limit and i >= limit:
            break

        held_out = normalise(alias.name)
        scored: list[tuple[float, int]] = []

        for pos in candidates_for(alias.name, index):
            if normalise(names[pos]) == held_out:
                continue
            scored.append((name_score(alias.name, names[pos]), pos))

        scored.sort(key=lambda t: -t[0])

        hit_score = 0.0
        rank_of_true: int | None = None
        for rank, (sc, pos) in enumerate(scored, start=1):
            if same_org(ents[pos], alias.ent_num):
                hit_score = sc
                rank_of_true = rank
                break

        top_score, top_pos = (scored[0] if scored else (0.0, -1))

        out.append(AliasResult(
            alias=alias.name,
            true_ent_num=alias.ent_num,
            hit_score=hit_score,
            top_score=top_score,
            top_ent_num=ents[top_pos] if top_pos >= 0 else None,
            top_name=names[top_pos] if top_pos >= 0 else None,
            rank_of_true=rank_of_true,
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
    aliases_operational: int     # caught AND ranked first
    recall: float
    operational_recall: float    # share caught at rank 1
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
        # Caught: the true organisation appears in the alert list at this
        # threshold, wherever it ranks.
        caught = sum(1 for r in alias_results if r.hit_score >= t)
        recall = caught / n_alias if n_alias else 0.0

        alerted = [r for r in alias_results if r.top_score >= t]

        # Caught AND ranked first. The gap between this and recall is how
        # often an analyst has to read past the top hit to find the real
        # match, which is a workload question rather than a detection one.
        operational = sum(1 for r in alias_results
                          if r.hit_score >= t and r.rank_of_true == 1)

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
    correct = sorted(r.hit_score for r in alias_results if r.hit_score > 0)
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
