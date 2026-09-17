#!/usr/bin/env python3
"""
Run the full study against live OFAC and registry data.

Executed by CI. Writes to evidence/, which is committed so every figure in the
README traces to the run that produced it.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from triage import (costs, decide, evaluate, ofac, penalties,  # noqa: E402
                    policy, population, resolve)
from triage.match import candidate_index  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--alias-limit", type=int, default=6000)
    ap.add_argument("--clean-limit", type=int, default=8000)
    ap.add_argument("--entities-only", action="store_true", default=True)
    ap.add_argument("--penalty-years", type=int, default=12)
    ap.add_argument("--cache", default=str(ROOT / ".cache"))
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    EVIDENCE.mkdir(parents=True, exist_ok=True)

    # ---- 1. the watchlist -------------------------------------------------
    print("=" * 72)
    print("OFAC SANCTIONS LIST")
    print("=" * 72)
    snapshot = ofac.load(cache_dir=args.cache)
    prov = snapshot.provenance()
    print(f"  entries     : {prov['entries']:,}")
    print(f"  entities    : {prov['entities']:,}")
    print(f"  individuals : {prov['individuals']:,}")
    print(f"  aliases     : {prov['aliases']:,}")
    print(f"  sdn sha256  : {prov['sdn_sha256'][:16]}...")

    # Entity screening: corporate names, which is what a corporate bank
    # screens and what the clean population consists of. Mixing individuals
    # into the watchlist while the population is all companies would compare
    # populations that are not comparable.
    entity_entries = snapshot.entities()
    keep = {e.ent_num for e in entity_entries}
    pairs = [(a, t) for a, t in snapshot.aliases_with_target()
             if a.ent_num in keep]

    # A real filter loads every published name, primary and alias alike.
    watchlist = evaluate.build_watchlist(entity_entries,
                                         [a for a, _ in pairs])
    print(f"\n  entity entries            : {len(entity_entries):,}")
    print(f"  aliases of those entities : {len(pairs):,}")
    print(f"  watchlist NAMES (primary + alias): {len(watchlist):,}")

    # ---- 2. the clean population -----------------------------------------
    print()
    print("=" * 72)
    print("CLEAN POPULATION")
    print("=" * 72)
    # Overlap removal must run against every name on the WATCHLIST, not just
    # primary entries. Screening happens against primaries and aliases alike,
    # so a company exactly matching an alias is a genuine sanctioned overlap
    # and counting it as a false positive would flatter the headline rate.
    watchlist_names = [w.name for w in watchlist]
    pop = population.load(watchlist_names,
                          limit=args.clean_limit, cache_dir=args.cache)
    pprov = pop.provenance()
    print(f"  source      : {pprov['source']}")
    print(f"  entities    : {pprov['count']:,}")
    print(f"  removed as genuinely sanctioned: "
          f"{pprov['removed_sanctioned_overlaps']}")
    if pop.removed_overlaps:
        for n in pop.removed_overlaps[:5]:
            print(f"      - {n}")

    # ---- 3. screening -----------------------------------------------------
    print()
    print("=" * 72)
    print("SCREENING")
    print("=" * 72)
    names = [w.name for w in watchlist]
    index = candidate_index(names)
    print(f"  blocking index: {len(index):,} keys")

    # Resolve listings to organisations before measuring recall.
    clustering = resolve.build(watchlist)
    csum = clustering.summary()
    print(f"  listings -> organisations: {csum['entities']:,} -> "
          f"{csum['clusters']:,}")
    print(f"  multi-listing organisations: {csum['multi_listing_clusters']:,}")
    for a, b in csum["examples"][:3]:
        print(f"      merged: {a[:36]!r} + {b[:36]!r}")

    alias_results = evaluate.screen_aliases(pairs, watchlist, index,
                                            limit=args.alias_limit,
                                            clustering=clustering)

    unreachable = [r_ for r_ in alias_results if r_.hit_score == 0.0]
    print(f"\n  aliases with NO candidate at any threshold: "
          f"{len(unreachable):,} ({len(unreachable)/max(1,len(alias_results)):.1%})")
    for r_ in unreachable[:6]:
        print(f"      {r_.alias[:48]!r}")
    clean_results = evaluate.screen_clean(pop.entities, watchlist, index,
                                          limit=args.clean_limit)
    print(f"  aliases screened : {len(alias_results):,}")
    print(f"  clean screened   : {len(clean_results):,}")

    sep = evaluate.separation(alias_results, clean_results)
    if sep:
        print(f"\n  alias median score : {sep['alias_median']:.1f}")
        print(f"  clean median score : {sep['clean_median']:.1f}")
        print(f"  clean 95th pct     : {sep['clean_p95']:.1f}")
        print(f"  distributions overlap: {sep['distributions_overlap']}")

    # ---- 4. threshold sweep ----------------------------------------------
    points = evaluate.sweep(alias_results, clean_results)
    print()
    print("=" * 72)
    print("THRESHOLD SWEEP")
    print("=" * 72)
    print(f"  {'thr':>4} {'recall':>8} {'op.recall':>10} "
          f"{'FP rate':>9} {'alerts/10k':>11}")
    for p in points:
        if int(p.threshold) % 4 == 0:
            print(f"  {p.threshold:4.0f} {p.recall:8.1%} "
                  f"{p.operational_recall:10.1%} "
                  f"{p.false_positive_rate:9.2%} {p.alerts_per_10k:11.1f}")

    # ---- 5. penalties -----------------------------------------------------
    print()
    print("=" * 72)
    print("OFAC ENFORCEMENT RECORD")
    print("=" * 72)
    years = list(range(2026 - args.penalty_years, 2026))
    record = penalties.fetch(years)
    psum = record.summary()
    if psum.get("count"):
        print(f"  actions with amounts : {psum['count']:,} ({psum['years']})")
        print(f"  median penalty       : ${psum['median_usd']:,.0f}")
        print(f"  mean penalty         : ${psum['mean_usd']:,.0f}")
        print(f"  90th percentile      : ${psum['p90_usd']:,.0f}")
        print(f"  largest              : ${psum['max_usd']:,.0f}")
    if record.years_failed:
        print(f"  years not parsed     : {record.years_failed}")

    # ---- 5b. does the ceiling hold for individuals? ------------------------
    #
    # The headline rests on entity aliases, which skew toward acronyms and
    # trading names. Most real sanctions false positives come from
    # transliterated INDIVIDUAL names, which skew toward spelling variants
    # that fuzzy matching does reach. If the unreachable rate is much lower
    # for individuals, the recommendation is wrong for the population a bank
    # screens most, and that objection deserves a measurement rather than a
    # caveat.
    #
    # Only the recall side is run here. Measuring false positives for
    # individuals would need a corpus of innocent people's names, and
    # publishing near-misses between real private individuals and a sanctions
    # list is an exposure this project will not create.
    print()
    print("=" * 72)
    print("DOES THE CEILING HOLD FOR INDIVIDUALS?")
    print("=" * 72)
    indiv_entries = snapshot.individuals()
    indiv_keep = {e.ent_num for e in indiv_entries}
    indiv_pairs = [(a, t) for a, t in snapshot.aliases_with_target()
                   if a.ent_num in indiv_keep]

    if indiv_pairs:
        indiv_watchlist = evaluate.build_watchlist(
            indiv_entries, [a for a, _ in indiv_pairs])
        indiv_index = candidate_index([w.name for w in indiv_watchlist])
        indiv_clustering = resolve.build(indiv_watchlist)
        indiv_results = evaluate.screen_aliases(
            indiv_pairs, indiv_watchlist, indiv_index,
            limit=args.alias_limit, clustering=indiv_clustering)

        indiv_unreachable = [r_ for r_ in indiv_results if r_.hit_score == 0.0]
        ent_rate = len(unreachable) / max(1, len(alias_results))
        ind_rate = len(indiv_unreachable) / max(1, len(indiv_results))

        indiv_points = evaluate.sweep(indiv_results, [])
        best_indiv = max(indiv_points, key=lambda x: x.recall)

        print(f"  individual listings     : {len(indiv_entries):,}")
        print(f"  individual aliases      : {len(indiv_pairs):,}")
        print(f"  screened                : {len(indiv_results):,}")
        print()
        print(f"  unreachable — ENTITIES    : {ent_rate:.1%} "
              f"({len(unreachable):,}/{len(alias_results):,})")
        print(f"  unreachable — INDIVIDUALS : {ind_rate:.1%} "
              f"({len(indiv_unreachable):,}/{len(indiv_results):,})")
        print(f"  max recall — individuals  : {best_indiv.recall:.1%}")
        print()
        if ind_rate < ent_rate * 0.6:
            print("  The ceiling is MUCH lower for individuals. The headline")
            print("  recommendation is scoped to entity screening and should")
            print("  not be carried to personal-name screening unchanged.")
        elif ind_rate > ent_rate * 1.4:
            print("  The ceiling is HIGHER for individuals, strengthening the")
            print("  recommendation rather than qualifying it.")
        else:
            print("  The ceiling holds across both populations, which removes")
            print("  the main scope objection to the recommendation.")
        for r_ in indiv_unreachable[:5]:
            print(f"      {r_.alias[:48]!r}")

        individuals_summary = {
            "listings": len(indiv_entries),
            "aliases_screened": len(indiv_results),
            "unreachable_count": len(indiv_unreachable),
            "unreachable_rate": ind_rate,
            "entity_unreachable_rate": ent_rate,
            "max_recall": best_indiv.recall,
            "scope_note": (
                "Recall side only. Measuring false positives for individuals "
                "would require a corpus of innocent people's names, and "
                "publishing near-misses between real private individuals and a "
                "sanctions list is an exposure this project will not create."
            ),
        }
    else:
        individuals_summary = {}
        print("  no individual aliases available")

    # ---- 6. the decision --------------------------------------------------
    assumptions = costs.CostAssumptions()
    anchors = penalties.loss_anchors(record)
    if anchors.get("p90"):
        assumptions.penalty_per_enforcement = anchors["p90"]
        print(f"\n  loss anchor set to the observed 90th percentile: "
              f"${anchors['p90']:,.0f}")

    rec = decide.recommend(points, assumptions=assumptions, separation=sep)

    print()
    print("=" * 72)
    print("RECOMMENDATION")
    print("=" * 72)
    if rec.cost_optimal:
        o = rec.cost_optimal
        print(f"  cost-optimal threshold : {o.threshold:.0f}")
        print(f"    recall               : {o.recall:.1%}")
        print(f"    alerts per 10k       : {o.alerts_per_10k:.1f}")
        print(f"    annual review cost   : ${o.review_cost:,.0f}")
        print(f"    annual exposure      : ${o.exposure_cost:,.0f}")
        print(f"    total                : ${o.total_cost:,.0f}")
        print(f"    analyst FTE          : {o.analyst_fte:.1f}")
    if rec.recall_constrained:
        r = rec.recall_constrained
        print(f"\n  cheapest at {rec.recall_floor:.0%} recall floor: "
              f"threshold {r.threshold:.0f}")
        print(f"    recall               : {r.recall:.1%}")
        print(f"    total                : ${r.total_cost:,.0f}")

    print(f"\n  stable under   : {', '.join(rec.stable_parameters) or 'none'}")
    print(f"  UNSTABLE under : {', '.join(rec.unstable_parameters) or 'none'}")

    # ---- tiered policy and operating range --------------------------------
    print()
    print("=" * 72)
    print("OPERATING RANGE (tiered policy)")
    print("=" * 72)
    rng = policy.operating_range(points, assumptions)
    if rng.policies:
        print(f"  defensible auto-clear floor: {rng.floor_low:.0f} - "
              f"{rng.floor_high:.0f}")
        print(f"    at the low end : {rng.constraint_low}")
        print(f"    at the high end: {rng.constraint_high}")
        print()
        print(f"  {'floor':>5} {'recall':>8} {'alerts/10k':>11} "
              f"{'FTE':>7} {'missed/yr':>10} {'total $':>14}")
        for pol in sorted(rng.policies, key=lambda x: x.auto_clear_below):
            print(f"  {pol.auto_clear_below:5.0f} {pol.recall_at_floor:8.1%} "
                  f"{pol.alerts_per_10k:11.1f} {pol.analyst_fte:7.1f} "
                  f"{pol.missed_below_floor:10.2f} "
                  f"${pol.total_cost:13,.0f}")
    else:
        print(f"  NO viable policy: {rng.constraint_low}; {rng.constraint_high}")

    all_policies = policy.search_policies(points, assumptions)
    best_policy = min(all_policies, key=lambda x: x.total_cost) if all_policies else None
    if best_policy:
        print()
        print(f"  cheapest tiered policy: auto-clear below "
              f"{best_policy.auto_clear_below:.0f}, escalate above "
              f"{best_policy.escalate_above:.0f}")
        print(f"    recall at floor : {best_policy.recall_at_floor:.1%}")
        print(f"    analyst FTE     : {best_policy.analyst_fte:.1f}")
        print(f"    total cost      : ${best_policy.total_cost:,.0f}")

    # ---- the alerts an analyst actually sees ------------------------------
    print()
    print("=" * 72)
    print("WHAT A FALSE POSITIVE LOOKS LIKE")
    print("=" * 72)
    worst = sorted(clean_results, key=lambda r_: -r_.score)[:10]
    for r_ in worst:
        print(f"  {r_.score:5.1f}  {r_.name[:44]:46s} vs {str(r_.top_match)[:40]}")

    # ---- 7. evidence ------------------------------------------------------
    (EVIDENCE / "provenance.json").write_text(json.dumps({
        "ofac": prov, "population": pprov,
        "entity_resolution": csum,
        "individuals_comparison": individuals_summary,
        "unreachable_aliases": {
            "count": len(unreachable),
            "share": len(unreachable) / max(1, len(alias_results)),
            "examples": [r_.alias for r_ in unreachable[:40]],
            "note": (
                "Aliases generating no candidate at any threshold. Acronyms "
                "and unrelated trading names sharing no character sequence "
                "with any other published name for the same party. This is "
                "the floor on name-only screening: no metric and no threshold "
                "reaches them, because there is nothing to be similar to."
            ),
        },
        "penalties": psum,
        "watchlist_scope": "entities only (individuals excluded)",
        "aliases_screened": len(alias_results),
        "clean_screened": len(clean_results),
    }, indent=2))

    (EVIDENCE / "sweep.json").write_text(json.dumps(
        [p.as_dict() for p in points], indent=2))
    (EVIDENCE / "recommendation.json").write_text(json.dumps({
        **rec.as_dict(),
        "operating_range": rng.as_dict(),
        "best_tiered_policy": best_policy.as_dict() if best_policy else None,
        "worst_false_positives": [
            {"company": r_.name, "matched_sdn_name": r_.top_match,
             "score": r_.score, "sdn_ent_num": r_.top_ent_num}
            for r_ in sorted(clean_results, key=lambda x: -x.score)[:25]
        ],
    }, indent=2, default=float))
    (EVIDENCE / "penalties.json").write_text(json.dumps({
        "summary": psum,
        "actions": [asdict(p) for p in record.penalties],
    }, indent=2))

    import csv
    with (EVIDENCE / "alias_results.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=[
            "alias", "true_ent_num", "hit_score", "top_score",
            "top_ent_num", "top_name", "rank_of_true"])
        w.writeheader()
        for r in alias_results:
            w.writerow(asdict(r))
    with (EVIDENCE / "clean_results.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["name", "identifier", "top_match",
                                           "top_ent_num", "score"])
        w.writeheader()
        for r in clean_results:
            w.writerow(asdict(r))

    print(f"\nEvidence written to {EVIDENCE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
