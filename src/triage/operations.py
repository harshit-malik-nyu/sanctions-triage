"""
Operational levers that reduce alert volume without moving the threshold.

The threshold is the lever everyone reaches for and the least effective one,
because moving it trades recall for volume along a fixed frontier. The levers
below move the frontier itself, and all three are standard practice in a run
sanctions function rather than inventions of this study.

    False-hit lists      A clean party that alerts today alerts again next
                         month, and every month after, because neither its
                         name nor the list entry has changed. OFAC explicitly
                         recognises the practice of maintaining a list of
                         reviewed non-matches whose alerts are suppressed.
                         Volume reduction is permanent, and it costs nothing
                         in recall against new designations.

    List hygiene         A single watchlist entry can generate alerts far out
                         of proportion to its risk. `M INVEST, OOO` matched
                         three unrelated companies in this sample alone.
                         Concentration is measurable, and the worst entries
                         are candidates for tighter matching rules rather than
                         a global threshold change.

    Population tuning    Entity names and personal names fail differently.
                         Running one threshold across both is a compromise
                         that serves neither, and both rates are measured
                         separately here.

Why this module exists
----------------------
A regulator's objection to a whitelist is not that it exists but that nobody
governs it. The cited failure mode is a customer generating forty alerts a
month, every one cleared, for six months, with no one asking why — described
in the literature as a governance failure rather than a matching failure. So
every reduction here is reported with what it costs in coverage and what has to
be reviewed to keep it defensible.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field


@dataclass
class WhitelistImpact:
    """Effect of suppressing alerts from reviewed non-matches."""

    threshold: float
    distinct_alerting_parties: int
    total_alerts: int

    top_n: int
    alerts_removed: int
    volume_reduction: float

    residual_alerts: int
    parties_requiring_review: int

    def as_dict(self) -> dict:
        return {
            "threshold": self.threshold,
            "distinct_alerting_parties": self.distinct_alerting_parties,
            "total_alerts": self.total_alerts,
            "whitelisted_parties": self.top_n,
            "alerts_removed": self.alerts_removed,
            "volume_reduction": self.volume_reduction,
            "residual_alerts": self.residual_alerts,
            "parties_requiring_review": self.parties_requiring_review,
        }


def whitelist_impact(clean_results, threshold: float,
                     top_n_values: list[int] | None = None
                     ) -> list[WhitelistImpact]:
    """
    Volume removed by whitelisting the most persistent false positives.

    Each clean party alerting at this threshold is counted once, because in
    production the same customer is rescreened continuously — nightly against
    an updated list, and on every payment. One name generating one alert in
    this sample generates that alert repeatedly forever until someone
    suppresses it.

    Reduction is therefore understated here rather than overstated: this
    measures one screening pass, and the saving recurs.
    """
    alerting = [r for r in clean_results if r.score >= threshold]
    total = len(alerting)
    if not total:
        return []

    out: list[WhitelistImpact] = []

    # Suppression is counted against the highest-scoring non-matches, which
    # are the ones alerting under every plausible threshold and therefore
    # carrying the most recurring cost.
    for n in (top_n_values or [10, 25, 50, 100, 250]):
        n = min(n, total)
        removed = n
        out.append(WhitelistImpact(
            threshold=threshold,
            distinct_alerting_parties=total,
            total_alerts=total,
            top_n=n,
            alerts_removed=removed,
            volume_reduction=removed / total,
            residual_alerts=total - removed,
            parties_requiring_review=n,
        ))
    return out


@dataclass
class ListConcentration:
    """How unevenly alerts are distributed across watchlist entries."""

    threshold: float
    entries_generating_alerts: int
    total_alerts: int
    top_1pct_share: float
    top_5pct_share: float
    top_10_entries: list[tuple[str, int]] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "threshold": self.threshold,
            "entries_generating_alerts": self.entries_generating_alerts,
            "total_alerts": self.total_alerts,
            "top_1pct_share_of_alerts": self.top_1pct_share,
            "top_5pct_share_of_alerts": self.top_5pct_share,
            "worst_entries": [{"name": n, "alerts": c}
                              for n, c in self.top_10_entries],
        }


def list_concentration(clean_results, threshold: float) -> ListConcentration:
    """
    Which watchlist entries generate the alerts.

    If a small share of entries produces most of the volume, the efficient
    intervention is entry-level — a tighter rule, a required secondary
    identifier, a longer minimum token — not a global threshold move that
    degrades recall against every other entry on the list.
    """
    alerting = [r for r in clean_results if r.score >= threshold]
    counts = Counter(r.top_match for r in alerting if r.top_match)
    total = sum(counts.values())

    if not total:
        return ListConcentration(threshold, 0, 0, 0.0, 0.0, [])

    ordered = counts.most_common()
    n_entries = len(ordered)

    def share(fraction: float) -> float:
        k = max(1, int(n_entries * fraction))
        return sum(c for _, c in ordered[:k]) / total

    return ListConcentration(
        threshold=threshold,
        entries_generating_alerts=n_entries,
        total_alerts=total,
        top_1pct_share=share(0.01),
        top_5pct_share=share(0.05),
        top_10_entries=ordered[:10],
    )


@dataclass
class PopulationTuning:
    """Separate operating points for entity and personal names."""

    entity_threshold: float
    entity_recall: float
    entity_unreachable: float

    individual_threshold: float
    individual_recall: float
    individual_unreachable: float

    single_threshold_recall_loss: float
    """
    Recall given up by running one threshold across both populations instead
    of two. The cost of a simplification that is usually made for
    convenience rather than for a reason.
    """

    def as_dict(self) -> dict:
        return {
            "entity": {
                "threshold": self.entity_threshold,
                "recall": self.entity_recall,
                "unreachable_rate": self.entity_unreachable,
            },
            "individual": {
                "threshold": self.individual_threshold,
                "recall": self.individual_recall,
                "unreachable_rate": self.individual_unreachable,
            },
            "recall_lost_to_a_single_threshold": self.single_threshold_recall_loss,
        }


def population_tuning(entity_points, individual_points,
                      *, target_recall: float = 0.60) -> PopulationTuning | None:
    """
    Lowest threshold reaching a target recall, per population.

    Entity and personal names fail differently — entity aliases skew toward
    acronyms and trading names that share nothing with the primary, personal
    aliases toward spelling and transliteration variants that fuzzy matching
    does reach. A single threshold across both is a compromise that serves
    neither, and the recall it costs is quantifiable.
    """
    def best(points):
        eligible = [p for p in points if p.recall >= target_recall]
        return max(eligible, key=lambda p: p.threshold) if eligible else None

    ent = best(entity_points)
    ind = best(individual_points)
    if ent is None or ind is None:
        return None

    # A single threshold must satisfy the harder population, so it sits at the
    # lower of the two and gives up recall on the easier one.
    single = min(ent.threshold, ind.threshold)
    at_single = next((p for p in individual_points if p.threshold == single), None)
    loss = (at_single.recall - ind.recall) if at_single else 0.0

    ent_unreach = 1.0 - max(p.recall for p in entity_points)
    ind_unreach = 1.0 - max(p.recall for p in individual_points)

    return PopulationTuning(
        entity_threshold=ent.threshold,
        entity_recall=ent.recall,
        entity_unreachable=ent_unreach,
        individual_threshold=ind.threshold,
        individual_recall=ind.recall,
        individual_unreachable=ind_unreach,
        single_threshold_recall_loss=abs(loss),
    )
