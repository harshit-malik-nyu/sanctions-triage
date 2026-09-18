"""
Tests for the analytical core.

These target the properties that make the headline defensible rather than the
code that happens to be untested. Several pin a specific error that was made
and corrected, because each one produced a plausible-looking number and none
would have been caught by looking at the rate.
"""

from __future__ import annotations

import pytest

from triage import costs, evaluate, ofac, policy, resolve
from triage.evaluate import AliasResult, CleanResult, WatchlistName


# ===========================================================================
# OFAC parsing
# ===========================================================================

SDN_SAMPLE = '''36,"AEROCARIBBEAN AIRLINES",-0- ,"CUBA",-0- ,-0- ,-0- ,-0- ,-0- ,-0- ,-0- ,-0-
173,"ANGLO-CARIBBEAN CO., LTD.",-0- ,"CUBA",-0- ,-0- ,-0- ,-0- ,-0- ,-0- ,-0- ,-0-
306,"BANCO NACIONAL DE CUBA","individual","CUBA","Title here",-0- ,-0- ,-0- ,-0- ,-0- ,-0- ,"a remark"
'''

ALT_SAMPLE = '''36,12,"aka","AERO-CARIBBEAN",-0-
306,220,"aka","BNC",-0-
9999,1,"aka","ORPHAN ALIAS",-0-
'''


class TestOfacParsing:

    def test_entries_parsed(self):
        entries = ofac.parse_sdn(SDN_SAMPLE)
        assert len(entries) == 3
        assert entries[0].ent_num == 36
        assert entries[0].name == "AEROCARIBBEAN AIRLINES"

    def test_null_token_becomes_none(self):
        """OFAC encodes absent fields as the literal '-0-', not empty."""
        entries = ofac.parse_sdn(SDN_SAMPLE)
        assert entries[0].sdn_type is None
        assert entries[0].remarks is None

    def test_blank_type_means_entity_not_unknown(self):
        """
        A genuine encoding quirk. Reading blank as missing would discard the
        entire corporate population — which is what a corporate bank screens.
        """
        entries = ofac.parse_sdn(SDN_SAMPLE)
        assert entries[0].is_entity
        assert not entries[0].is_individual
        assert entries[2].is_individual

    def test_aliases_parsed_and_linked(self):
        aliases = ofac.parse_alt(ALT_SAMPLE)
        assert len(aliases) == 3
        assert aliases[0].ent_num == 36
        assert aliases[0].name == "AERO-CARIBBEAN"

    def test_orphan_aliases_excluded_from_ground_truth(self):
        """
        An alias whose parent entry is absent cannot be scored: there is no
        entity for a match to be correct against.
        """
        snap = ofac.OfacSnapshot(entries=ofac.parse_sdn(SDN_SAMPLE),
                                 aliases=ofac.parse_alt(ALT_SAMPLE))
        usable = snap.aliases_with_target()
        assert len(usable) == 2
        assert all(a.ent_num in snap.by_ent_num() for a, _ in usable)

    def test_malformed_rows_skipped_not_fatal(self):
        assert ofac.parse_sdn("garbage\n,,,\n") == []

    def test_truncated_list_is_refused(self):
        """
        An empty watchlist yields zero alerts and a flawless-looking
        false-positive rate. That is the most dangerous failure available
        here, because it looks like success.
        """
        with pytest.raises(ofac.OfacUnavailable):
            ofac.fetch_with_fallback("http://127.0.0.1:9/a",
                                     "http://127.0.0.1:9/b", "SDN list")


# ===========================================================================
# Entity resolution
# ===========================================================================

class TestEntityResolution:

    def _wl(self, rows):
        return [WatchlistName(n, e, True) for n, e in rows]

    def test_word_order_variants_merge(self):
        """
        REGRESSION. POPULAR REVOLUTIONARY STRUGGLE matched REVOLUTIONARY
        POPULAR STRUGGLE at 100 and was scored a miss, because the entity
        numbers differed. OFAC designates the same group more than once.
        """
        c = resolve.build(self._wl([
            ("POPULAR REVOLUTIONARY STRUGGLE", 100),
            ("REVOLUTIONARY POPULAR STRUGGLE", 200),
        ]))
        assert c.same_org(100, 200)

    def test_distinct_organisations_do_not_merge(self):
        """
        The dangerous direction. Merging distinct organisations converts
        genuine misses into apparent catches and inflates recall.
        """
        c = resolve.build(self._wl([
            ("BANK OF CHINA", 1),
            ("BANK OF AMERICA", 2),
            ("AL-AQSA FOUNDATION", 3),
            ("AL-AQSA ISLAMIC CHARITABLE SOCIETY", 4),
        ]))
        assert not c.same_org(1, 2)
        assert not c.same_org(3, 4)

    def test_merge_threshold_is_high(self):
        assert resolve.SAME_ORG_THRESHOLD >= 95.0

    def test_an_entity_is_always_its_own_organisation(self):
        c = resolve.build(self._wl([("SOLO ENTITY LTD", 7)]))
        assert c.same_org(7, 7)

    def test_none_never_matches(self):
        c = resolve.build(self._wl([("ANYTHING", 1)]))
        assert not c.same_org(None, 1)
        assert not c.same_org(1, None)

    def test_clustering_is_transitive(self):
        c = resolve.build(self._wl([
            ("GLOBAL TRADING COMPANY LIMITED", 1),
            ("GLOBAL TRADING CO LTD", 2),
            ("GLOBAL TRADING COMPANY LTD", 3),
        ]))
        assert c.same_org(1, 3)


# ===========================================================================
# Hold-one-out screening
# ===========================================================================

class TestHoldOneOut:

    def _watchlist(self):
        return [
            WatchlistName("AEROCARIBBEAN AIRLINES", 36, True),
            WatchlistName("AERO-CARIBBEAN", 36, False),
            WatchlistName("UNRELATED HOLDINGS LIMITED", 99, True),
        ]

    def test_the_alias_under_test_is_excluded(self):
        """
        Without exclusion the alias matches itself at 100 and the measurement
        is circular: near-perfect recall, nothing tested.
        """
        alias = ofac.Alias(ent_num=36, alt_num=1, alt_type="aka",
                           name="AERO-CARIBBEAN")
        [r] = evaluate.screen_aliases([(alias, None)], self._watchlist())
        assert r.hit_score < 100.0
        assert r.hit_score > 0          # still reachable via the primary name

    def test_exclusion_is_by_string_not_position(self):
        """
        The same name appears under several entity numbers; excluding one
        position would readmit the self-match through a duplicate.
        """
        wl = self._watchlist() + [WatchlistName("AERO-CARIBBEAN", 36, False)]
        alias = ofac.Alias(36, 1, "aka", "AERO-CARIBBEAN")
        [r] = evaluate.screen_aliases([(alias, None)], wl)
        assert r.hit_score < 100.0

    def test_unreachable_alias_scores_zero(self):
        """
        The finding the recommendation rests on: an alias sharing no character
        sequence with any other published name is unreachable at any
        threshold.
        """
        alias = ofac.Alias(36, 1, "aka", "COIBA")
        [r] = evaluate.screen_aliases([(alias, None)], self._watchlist())
        assert r.hit_score == 0.0
        assert resolve.unreachable_aliases([r]) == [r]

    def test_rank_records_how_far_an_analyst_reads(self):
        alias = ofac.Alias(36, 1, "aka", "AERO-CARIBBEAN")
        [r] = evaluate.screen_aliases([(alias, None)], self._watchlist())
        assert r.rank_of_true == 1

    def test_recall_counts_a_hit_anywhere_in_the_list(self):
        """
        REGRESSION. Top-1 scoring counted a correct answer at rank 2 as a
        miss. A filter returns every hit above threshold and an analyst works
        the list.
        """
        results = [AliasResult(alias="x", true_ent_num=1, hit_score=80.0,
                               top_score=95.0, top_ent_num=2, top_name="other",
                               rank_of_true=3)]
        [point] = evaluate.sweep(results, [], thresholds=[75.0])
        assert point.recall == 1.0
        assert point.operational_recall == 0.0   # caught, but not at rank 1


# ===========================================================================
# Sweep arithmetic
# ===========================================================================

class TestSweep:

    def _aliases(self, scores):
        return [AliasResult(alias=f"a{i}", true_ent_num=i, hit_score=s,
                            top_score=s, top_ent_num=i, top_name="n",
                            rank_of_true=1)
                for i, s in enumerate(scores)]

    def _clean(self, scores):
        return [CleanResult(name=f"c{i}", identifier=str(i), top_match="m",
                            top_ent_num=1, score=s)
                for i, s in enumerate(scores)]

    def test_recall_and_fpr_computed(self):
        points = evaluate.sweep(self._aliases([90, 80, 70, 60]),
                                self._clean([95, 50, 40, 30]),
                                thresholds=[75.0])
        p = points[0]
        assert p.recall == 0.5
        assert p.false_positive_rate == 0.25
        assert p.alerts_per_10k == 2500.0

    def test_recall_is_monotonic_decreasing_in_threshold(self):
        points = evaluate.sweep(self._aliases([95, 85, 75, 65]),
                                self._clean([60, 50]),
                                thresholds=[60.0, 70.0, 80.0, 90.0])
        recalls = [p.recall for p in points]
        assert recalls == sorted(recalls, reverse=True)

    def test_empty_inputs_do_not_divide_by_zero(self):
        [p] = evaluate.sweep([], [], thresholds=[80.0])
        assert p.recall == 0.0 and p.false_positive_rate == 0.0

    def test_wilson_bounds_stay_inside_zero_one(self):
        lo, hi = evaluate.wilson_interval(0, 40)
        assert lo == 0.0 and 0 < hi < 1
        lo, hi = evaluate.wilson_interval(40, 40)
        assert hi == 1.0 and 0 < lo < 1

    def test_separation_reports_overlap(self):
        sep = evaluate.separation(self._aliases([90, 85, 80]),
                                  self._clean([88, 70, 60]))
        assert "distributions_overlap" in sep


# ===========================================================================
# Cost model
# ===========================================================================

class TestCostModel:

    def test_review_cost_is_inside_the_published_band(self):
        """Published benchmarks put direct review cost at $15-25 per alert."""
        assert 15.0 <= float(costs.REVIEW_COST_PER_ALERT) <= 25.0

    def test_cost_inputs_are_mostly_published(self):
        reg = costs.registry()
        published = sum(1 for p in reg.values()
                        if p.evidence is costs.Evidence.PUBLISHED)
        estimate = sum(1 for p in reg.values()
                       if p.evidence is costs.Evidence.ESTIMATE)
        assert published > estimate

    def test_asymmetry_is_large_and_in_the_right_direction(self):
        """
        A missed designation costs orders of magnitude more than a wasted
        review. This is why precision-optimal thresholds target the wrong
        quantity.
        """
        a = costs.CostAssumptions()
        assert a.asymmetry_ratio > 100

    def test_sensitivity_runs_cannot_leak_state(self):
        """
        Assumptions are a mutable copy per run. A sweep that mutated module
        globals would make results depend on evaluation order.
        """
        base = costs.CostAssumptions()
        trial = costs.CostAssumptions(**{**base.__dict__,
                                         "review_cost_per_alert": 999.0})
        assert base.review_cost_per_alert != 999.0
        assert trial.review_cost_per_alert == 999.0

    def test_perfect_recall_leaves_no_exposure(self):
        out = costs.expected_annual_cost(
            alerts_per_screening=0.01, recall=1.0,
            assumptions=costs.CostAssumptions())
        assert out["exposure_cost"] == 0.0
        assert out["review_cost"] > 0

    def test_zero_alerts_still_carries_exposure(self):
        """A filter that alerts on nothing is free and catches nothing."""
        out = costs.expected_annual_cost(
            alerts_per_screening=0.0, recall=0.0,
            assumptions=costs.CostAssumptions())
        assert out["review_cost"] == 0.0
        assert out["exposure_cost"] > 0


# ===========================================================================
# Tiered policy
# ===========================================================================

class TestTieredPolicy:

    def _points(self):
        return evaluate.sweep(
            [AliasResult(alias=f"a{i}", true_ent_num=i, hit_score=s,
                         top_score=s, top_ent_num=i, top_name="n",
                         rank_of_true=1)
             for i, s in enumerate([95, 90, 85, 80, 75, 70, 65, 60])],
            [CleanResult(name=f"c{i}", identifier=str(i), top_match="m",
                         top_ent_num=1, score=s)
             for i, s in enumerate([92, 70, 65, 60, 55, 50, 45, 40])],
            thresholds=[60.0, 70.0, 80.0, 90.0])

    def test_recall_at_floor_is_what_the_policy_risks(self):
        """
        Everything below the floor is discarded with no human in the loop, so
        recall at the floor is the entire detection guarantee.
        """
        pol = policy.evaluate_policy(self._points(), 70.0, 90.0,
                                     costs.CostAssumptions())
        assert pol is not None
        by_t = {p.threshold: p for p in self._points()}
        assert pol.recall_at_floor == by_t[70.0].recall

    def test_raising_the_floor_cuts_alerts_and_recall_together(self):
        a = costs.CostAssumptions()
        low = policy.evaluate_policy(self._points(), 60.0, 90.0, a)
        high = policy.evaluate_policy(self._points(), 80.0, 90.0, a)
        assert high.alerts_per_10k <= low.alerts_per_10k
        assert high.recall_at_floor <= low.recall_at_floor

    def test_escalation_costs_more_per_item(self):
        assert policy.ESCALATION_COST_MULTIPLE > 1.0

    def test_unknown_thresholds_return_none(self):
        assert policy.evaluate_policy(self._points(), 61.0, 90.0,
                                      costs.CostAssumptions()) is None

    def test_search_respects_a_minimum_band(self):
        found = policy.search_policies(self._points(), costs.CostAssumptions(),
                                       min_band=20.0)
        assert all(p.escalate_above - p.auto_clear_below >= 20.0 for p in found)

    def test_empty_operating_range_names_the_binding_constraints(self):
        """
        An unsatisfiable pair of constraints is the finding, not a failure to
        produce one. Relaxing until an answer appears would be the error.
        """
        rng = policy.operating_range(self._points(), costs.CostAssumptions(),
                                     max_fte=0.001, min_recall=0.999)
        assert rng.policies == []
        assert "staffing" in rng.constraint_low or "FTE" in rng.constraint_low
        assert "recall" in rng.constraint_high


# ===========================================================================
# Population integrity
# ===========================================================================

class TestPopulationOverlap:

    def test_exact_sdn_matches_are_detected(self):
        """
        Counting a genuine sanctioned party as a false positive would flatter
        the headline rate in the convenient direction.
        """
        from triage.population import find_overlaps
        found = find_overlaps(["ARGO S.R.L.", "SOME CLEAN COMPANY LTD"],
                              ["ARGO SRL", "OTHER SANCTIONED ENTITY"])
        assert found == {"ARGO S.R.L."}

    def test_overlap_check_is_exact_not_fuzzy(self):
        """
        A fuzzy check here would delete the near-misses the study exists to
        count, improving the result by construction.
        """
        from triage.population import find_overlaps
        assert find_overlaps(["IRIS MARINE SERVICES"],
                             ["IRISL MARINE SERVICES"]) == set()


# ===========================================================================
# Penalty parsing — the anchor for the loss side
# ===========================================================================

PENALTY_PAGE = """
<table>
<tr><th>Date</th><th>Name</th><th>Count</th><th>Penalty</th></tr>
<tr><td>01/15/2024</td><td>Example Bank N.A.</td><td>12</td><td>$1,500,000</td></tr>
<tr><td>03/02/2024</td><td>Small Trading Co</td><td>2</td><td>$45,000.00</td></tr>
<tr><td>06/20/2024</td><td>Finding Of Violation Corp</td><td>1</td><td>N/A</td></tr>
<tr><td>09/11/2024</td><td>Global Institution PLC</td><td>340</td><td>$92,000,000</td></tr>
<tr><td>Header row that is not a date</td><td>x</td><td>y</td><td>z</td></tr>
</table>
"""


class TestPenaltyParsing:

    def test_rows_with_amounts_parsed(self):
        from triage import penalties
        rows = penalties.parse_year(PENALTY_PAGE, 2024)
        assert len(rows) == 4
        amounts = [r.amount_usd for r in rows if r.has_amount]
        assert 1_500_000.0 in amounts
        assert 45_000.0 in amounts

    def test_findings_without_a_penalty_are_kept_but_unvalued(self):
        """
        OFAC issues findings of violation with no monetary penalty. Dropping
        them would overstate the average cost of an enforcement action.
        """
        from triage import penalties
        rows = penalties.parse_year(PENALTY_PAGE, 2024)
        no_amount = [r for r in rows if not r.has_amount]
        assert len(no_amount) == 1
        assert "Finding" in no_amount[0].counterparty

    def test_non_date_rows_skipped(self):
        from triage import penalties
        assert all(r.date and "/" in r.date
                   for r in penalties.parse_year(PENALTY_PAGE, 2024))

    def test_empty_page_yields_nothing(self):
        from triage import penalties
        assert penalties.parse_year("<html>no table</html>", 2024) == []

    def test_summary_reports_median_and_mean_separately(self):
        """
        They differ by orders of magnitude because a few institutional
        settlements dominate. Quoting one alone would misrepresent the
        distribution.
        """
        from triage import penalties
        rec = penalties.PenaltyRecord(
            penalties=penalties.parse_year(PENALTY_PAGE, 2024),
            years_fetched=[2024])
        s = rec.summary()
        # With three amounts dominated by one large settlement, the mean sits
        # well above the median — the shape of OFAC's actual distribution and
        # the reason the study reports both.
        assert s["count"] == 3
        assert s["mean_usd"] > s["median_usd"] * 2

    def test_loss_anchors_offers_three_choices(self):
        """
        Which anchor to use is a judgment. Hiding it inside a single number
        would misrepresent how much the answer depends on it.
        """
        from triage import penalties
        rec = penalties.PenaltyRecord(
            penalties=penalties.parse_year(PENALTY_PAGE, 2024),
            years_fetched=[2024])
        anchors = penalties.loss_anchors(rec)
        assert set(anchors) == {"median", "mean", "p90"}

    def test_no_data_yields_no_anchors_rather_than_zero(self):
        from triage import penalties
        assert penalties.loss_anchors(penalties.PenaltyRecord()) == {}


# ===========================================================================
# The decision layer
# ===========================================================================

class TestDecision:

    def _points(self):
        from triage.evaluate import AliasResult, CleanResult
        return evaluate.sweep(
            [AliasResult(alias=f"a{i}", true_ent_num=i, hit_score=s,
                         top_score=s, top_ent_num=i, top_name="n",
                         rank_of_true=1)
             for i, s in enumerate([98, 94, 90, 86, 82, 78, 74, 70, 66, 62])],
            [CleanResult(name=f"c{i}", identifier=str(i), top_match="m",
                         top_ent_num=1, score=s)
             for i, s in enumerate([96, 88, 80, 72, 64, 56, 48, 40, 32, 24])],
            thresholds=[60.0, 70.0, 80.0, 90.0, 100.0])

    def test_optimum_minimises_total_cost(self):
        from triage import decide
        opts = decide.cost_options(self._points(), costs.CostAssumptions())
        best = decide.optimal(opts)
        assert best.total_cost == min(o.total_cost for o in opts)

    def test_recall_floor_option_respects_the_floor(self):
        """
        A regulator does not accept 'the expected value worked' as an answer
        for a missed designation, so a recall-constrained option is reported
        alongside the cost optimum.
        """
        from triage import decide
        opts = decide.cost_options(self._points(), costs.CostAssumptions())
        got = decide.minimum_acceptable_recall(opts, floor=0.5)
        assert got is None or got.recall >= 0.5

    def test_unreachable_recall_floor_returns_none(self):
        from triage import decide
        opts = decide.cost_options(self._points(), costs.CostAssumptions())
        assert decide.minimum_acceptable_recall(opts, floor=1.01) is None

    def test_sensitivity_reports_instability(self):
        """
        The central honesty property. If the recommendation moves further than
        one sweep step across a plausible range of an unvalidated input, it is
        a restatement of the assumption rather than a recommendation.
        """
        from triage import decide
        sens = decide.sweep_assumption(
            self._points(), "p_miss_becomes_enforcement",
            [0.001, 0.01, 0.1, 0.5])
        lo, hi = sens.threshold_range
        assert sens.is_stable == ((hi - lo) <= 6.0)

    def test_every_contested_assumption_is_swept(self):
        from triage import decide
        names = {s.parameter for s in decide.full_sensitivity(self._points())}
        assert {"p_miss_becomes_enforcement", "penalty_per_enforcement",
                "review_cost_per_alert", "true_sanctioned_rate"} <= names

    def test_sensitivity_does_not_mutate_the_base_assumptions(self):
        from triage import decide
        base = costs.CostAssumptions()
        before = base.review_cost_per_alert
        decide.full_sensitivity(self._points(), base)
        assert base.review_cost_per_alert == before

    def test_recommendation_separates_stable_from_unstable(self):
        from triage import decide
        rec = decide.recommend(self._points())
        overlap = set(rec.stable_parameters) & set(rec.unstable_parameters)
        assert not overlap

    def test_recommendation_serialises(self):
        from triage import decide
        d = decide.recommend(self._points()).as_dict()
        assert "cost_optimal" in d and "sensitivities" in d
        assert "unstable_under" in d


# ===========================================================================
# Population loading
# ===========================================================================

class TestPopulationLoading:

    def test_sec_response_shape_is_handled(self):
        """
        The endpoint returns a JSON object keyed by row index rather than a
        list — a quirk of the endpoint, not the data.
        """
        import json as _json
        from unittest.mock import patch
        from triage import population

        payload = _json.dumps({
            "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
            "1": {"cik_str": 789019, "ticker": "MSFT", "title": "Microsoft Corp"},
        }).encode()
        with patch.object(population, "_get", return_value=payload):
            out = population.fetch_sec()
        assert [e.name for e in out] == ["Apple Inc.", "Microsoft Corp"]
        assert out[0].identifier == "CIK320193"

    def test_entries_without_a_name_are_skipped(self):
        import json as _json
        from unittest.mock import patch
        from triage import population

        payload = _json.dumps({"0": {"cik_str": 1, "title": ""},
                               "1": {"cik_str": 2, "title": "Real Co"}}).encode()
        with patch.object(population, "_get", return_value=payload):
            assert len(population.fetch_sec()) == 1

    def test_gleif_records_parsed(self):
        import json as _json
        from unittest.mock import patch
        from triage import population

        page = _json.dumps({"data": [{
            "id": "LEI123",
            "attributes": {
                "lei": "LEI123",
                "entity": {"legalName": {"name": "Global Trading AB"},
                           "legalAddress": {"country": "SE"}},
            }}]}).encode()
        with patch.object(population, "_get", return_value=page):
            out = population.fetch_gleif(limit=1)
        assert out[0].name == "Global Trading AB"
        assert out[0].country == "SE"

    def test_all_sources_failing_raises_rather_than_returning_empty(self):
        """
        An empty population makes the false-positive rate undefined, and
        substituting generated names would put invented data at the centre of
        the headline number.
        """
        from unittest.mock import patch
        from triage import population

        with patch.object(population, "fetch_sec", side_effect=OSError("down")), \
             patch.object(population, "fetch_gleif", side_effect=OSError("down")):
            with pytest.raises(population.PopulationUnavailable):
                population.load(["SOME SDN NAME"])

    def test_a_thin_source_is_rejected_and_the_next_tried(self):
        from unittest.mock import patch
        from triage import population

        thin = [population.Entity(name=f"Co {i}", identifier=str(i),
                                  source="SEC EDGAR") for i in range(5)]
        fat = [population.Entity(name=f"Firm {i}", identifier=str(i),
                                 source="GLEIF LEI") for i in range(800)]
        with patch.object(population, "fetch_sec", return_value=thin), \
             patch.object(population, "fetch_gleif", return_value=fat):
            pop = population.load([])
        assert pop.source == "GLEIF LEI"
        assert len(pop.entities) == 800

    def test_sanctioned_overlaps_are_stripped_and_recorded(self):
        from unittest.mock import patch
        from triage import population

        entities = [population.Entity(name="ARGO SRL", identifier="1",
                                      source="GLEIF LEI")]
        entities += [population.Entity(name=f"Clean {i}", identifier=str(i + 2),
                                       source="GLEIF LEI") for i in range(700)]
        with patch.object(population, "fetch_sec", side_effect=OSError("down")), \
             patch.object(population, "fetch_gleif", return_value=entities):
            pop = population.load(["ARGO S.R.L."])
        assert "ARGO SRL" not in pop.names()
        assert pop.removed_overlaps == ["ARGO SRL"]
        assert pop.provenance()["removed_sanctioned_overlaps"] == 1


class TestCostAudit:

    def test_audit_lists_every_parameter_with_its_source(self):
        """
        The register is what makes the cost model auditable. A parameter
        missing from it is a number nobody can trace.
        """
        text = costs.audit()
        for name in costs.registry():
            assert name in text, f"{name} missing from the audit"

    def test_audit_separates_published_from_estimate(self):
        text = costs.audit()
        assert "[PUBLISHED]" in text
        assert "[ESTIMATE]" in text

    def test_audit_names_the_asymmetry_as_the_decision(self):
        text = costs.audit()
        assert "asymmetry ratio" in text
        assert "reported across a range" in text or "cannot be validated" in text

    def test_every_parameter_carries_a_source(self):
        for name, p in costs.registry().items():
            assert p.source, f"{name} has no source"

    def test_estimates_say_so_in_their_source(self):
        """
        An unvalidated number must be visibly unvalidated at the point a
        reader meets it, not only in a summary elsewhere.
        """
        for name, p in costs.registry().items():
            if p.evidence is costs.Evidence.ESTIMATE:
                assert "ESTIMATE" in p.source.upper(), (
                    f"{name} is an estimate but does not say so")


class TestOfacLoading:

    def test_load_parses_and_records_provenance(self, tmp_path):
        """
        The SDN list changes several times a week. Without the hash no figure
        can be tied to the data that produced it.
        """
        from unittest.mock import patch
        sdn = "\n".join(
            f'{i},"ENTITY NUMBER {i} TRADING LIMITED",-0- ,"CUBA",'
            + ",".join(["-0- "] * 8) for i in range(1200))
        alt = "\n".join(f'{i},1,"aka","ENTITY {i} ALIAS",-0-' for i in range(1200))

        with patch.object(ofac, "fetch_with_fallback",
                          side_effect=[sdn, alt]):
            snap = ofac.load(cache_dir=str(tmp_path))

        prov = snap.provenance()
        assert prov["entries"] == 1200
        assert prov["aliases"] == 1200
        assert len(prov["sdn_sha256"]) == 64
        assert prov["retrieved_utc"]

    def test_load_uses_the_cache_on_a_second_call(self, tmp_path):
        from unittest.mock import patch
        sdn = "\n".join(
            f'{i},"ENTITY {i} TRADING LIMITED",-0- ,"CUBA",'
            + ",".join(["-0- "] * 8) for i in range(1200))
        alt = f'1,1,"aka","AN ALIAS",-0-'

        with patch.object(ofac, "fetch_with_fallback",
                          side_effect=[sdn, alt]) as fetch:
            ofac.load(cache_dir=str(tmp_path))
            assert fetch.call_count == 2
            ofac.load(cache_dir=str(tmp_path))
            assert fetch.call_count == 2, "second load refetched instead of caching"

    def test_a_short_list_is_refused(self, tmp_path):
        """
        A truncated watchlist yields few alerts and a flattering
        false-positive rate. Reporting from it would be the most misleading
        possible result.
        """
        from unittest.mock import patch
        with patch.object(ofac, "fetch_with_fallback",
                          side_effect=['1,"ONLY ONE ENTRY LTD",-0- ,"CUBA"'
                                       + ",-0- " * 8, ""]):
            with pytest.raises(ofac.OfacUnavailable):
                ofac.load(cache_dir=str(tmp_path))
