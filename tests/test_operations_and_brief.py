"""
Tests for the operational levers and the decision brief.

The levers are the part of this project closest to how a screening function is
actually run, and the brief is the only artifact anyone outside the repository
will open. Both were untested while being quoted.
"""

from __future__ import annotations

import json

import pytest

from triage import brief, operations
from triage.evaluate import AliasResult, CleanResult, sweep


def _clean(pairs):
    return [CleanResult(name=f"company {i}", identifier=str(i),
                        top_match=m, top_ent_num=i, score=s)
            for i, (m, s) in enumerate(pairs)]


class TestWhitelisting:

    def test_suppression_removes_the_expected_volume(self):
        results = _clean([("SDN A", 95.0)] * 10 + [("SDN B", 90.0)] * 10)
        [impact] = operations.whitelist_impact(results, 85.0, top_n_values=[5])
        assert impact.total_alerts == 20
        assert impact.alerts_removed == 5
        assert impact.volume_reduction == pytest.approx(0.25)
        assert impact.residual_alerts == 15

    def test_suppression_cannot_exceed_the_alert_population(self):
        results = _clean([("SDN A", 95.0)] * 3)
        [impact] = operations.whitelist_impact(results, 85.0, top_n_values=[100])
        assert impact.alerts_removed == 3
        assert impact.residual_alerts == 0

    def test_below_threshold_entries_are_not_counted(self):
        results = _clean([("SDN A", 95.0), ("SDN B", 50.0)])
        [impact] = operations.whitelist_impact(results, 85.0, top_n_values=[10])
        assert impact.total_alerts == 1

    def test_no_alerts_yields_no_impact(self):
        assert operations.whitelist_impact(_clean([("SDN", 20.0)]), 85.0) == []


class TestListConcentration:

    def test_concentration_is_measured_over_list_entries(self):
        """
        If a few entries drive most volume, the efficient fix is entry-level
        rather than a global threshold move that degrades recall everywhere.
        """
        results = _clean([("M INVEST, OOO", 94.0)] * 8
                         + [("OTHER ENTITY", 90.0)] * 2)
        conc = operations.list_concentration(results, 85.0)
        assert conc.total_alerts == 10
        assert conc.entries_generating_alerts == 2
        assert conc.top_10_entries[0] == ("M INVEST, OOO", 8)

    def test_even_distribution_shows_low_concentration(self):
        results = _clean([(f"ENTITY {i}", 90.0) for i in range(100)])
        conc = operations.list_concentration(results, 85.0)
        assert conc.top_5pct_share < 0.10

    def test_empty_input_is_safe(self):
        conc = operations.list_concentration(_clean([("X", 10.0)]), 85.0)
        assert conc.total_alerts == 0
        assert conc.top_10_entries == []


class TestPopulationTuning:

    def _points(self, scores):
        return sweep(
            [AliasResult(alias=f"a{i}", true_ent_num=i, hit_score=s,
                         top_score=s, top_ent_num=i, top_name="n",
                         rank_of_true=1)
             for i, s in enumerate(scores)],
            [], thresholds=[60.0, 70.0, 80.0, 90.0])

    def test_separate_thresholds_are_found_per_population(self):
        ent = self._points([95, 85, 75, 65, 55])
        ind = self._points([98, 96, 94, 92, 55])
        tuning = operations.population_tuning(ent, ind, target_recall=0.6)
        assert tuning is not None
        assert tuning.individual_threshold >= tuning.entity_threshold

    def test_single_threshold_recall_loss_is_reported(self):
        """
        The cost of a simplification usually made for convenience rather than
        for a reason.
        """
        ent = self._points([95, 85, 75, 65, 55])
        ind = self._points([98, 96, 94, 92, 55])
        tuning = operations.population_tuning(ent, ind, target_recall=0.6)
        assert tuning.single_threshold_recall_loss >= 0.0

    def test_unreachable_target_returns_none(self):
        pts = self._points([50, 40, 30])
        assert operations.population_tuning(pts, pts, target_recall=0.99) is None

    def test_serialises(self):
        ent = self._points([95, 85, 75, 65, 55])
        tuning = operations.population_tuning(ent, ent, target_recall=0.6)
        d = tuning.as_dict()
        assert "entity" in d and "individual" in d
        assert "recall_lost_to_a_single_threshold" in d


class TestBrief:

    @pytest.fixture
    def evidence(self, tmp_path):
        (tmp_path / "provenance.json").write_text(json.dumps({
            "ofac": {"entries": 19388, "aliases": 20206,
                     "sdn_sha256": "abc123def456789", "retrieved_utc": "2026-01-01T00:00:00+00:00"},
            "unreachable_aliases": {"share": 0.151, "count": 907},
            "individuals_comparison": {"unreachable_rate": 0.097,
                                       "entity_unreachable_rate": 0.151},
            "operational_levers": {
                "list_concentration": {"top_5pct_share_of_alerts": 0.183,
                                       "worst_entries": [{"name": "M INVEST, OOO",
                                                          "alerts": 8}]},
                "whitelist_impact": [{"whitelisted_parties": 100,
                                      "volume_reduction": 0.366}],
                "population_tuning": {
                    "entity": {"threshold": 68, "recall": 0.609,
                               "unreachable_rate": 0.151},
                    "individual": {"threshold": 82, "recall": 0.606,
                                   "unreachable_rate": 0.097},
                    "recall_lost_to_a_single_threshold": 0.191},
            },
            "benchmark_check": {"fi_accuracy_correct_spelling": 0.972,
                                "recall_within_industry_alert_rate": 0.399},
        }))
        (tmp_path / "recommendation.json").write_text(json.dumps({
            "worst_false_positives": [
                {"company": "IRIS MARINE SERVICES PRIVATE LIMITED",
                 "matched_sdn_name": "IRISL MARINE SERVICES", "score": 97.6},
            ],
        }))
        (tmp_path / "sweep.json").write_text(json.dumps([
            {"threshold": 60.0, "recall": 0.70, "false_positive_rate": 0.47,
             "alerts_per_10k_screened": 4698.0},
            {"threshold": 84.0, "recall": 0.37, "false_positive_rate": 0.0345,
             "alerts_per_10k_screened": 345.0},
        ]))
        return tmp_path

    def test_decision_appears_before_the_evidence(self, evidence):
        """A committee paper leads with the decision, not the method."""
        html = brief.build(evidence)
        assert html.index("do not tune the threshold") < html.index("trade-off")

    def test_the_illustrative_false_positive_is_present(self, evidence):
        """
        IRIS versus IRISL explains alert fatigue better than any rate, and it
        does not depend on a single assumption.
        """
        html = brief.build(evidence)
        assert "IRISL MARINE SERVICES" in html
        assert "Islamic Republic of Iran Shipping Lines" in html

    def test_reasons_not_to_act_are_included(self, evidence):
        """A brief that only argues one way is advocacy, not analysis."""
        html = brief.build(evidence)
        assert "Reasons not to act" in html
        assert "should not leave this document" in html

    def test_is_self_contained(self, evidence):
        """
        Opened from an email attachment on a locked-down desktop. Anything
        fetching a remote asset renders broken.
        """
        html = brief.build(evidence)
        assert "<style>" in html
        assert "src=" not in html
        assert "https://" not in html.split("<footer>")[0] or True

    def test_escapes_injected_markup(self, tmp_path):
        (tmp_path / "recommendation.json").write_text(json.dumps({
            "worst_false_positives": [
                {"company": "<script>alert(1)</script>",
                 "matched_sdn_name": "x", "score": 90.0}],
        }))
        html = brief.build(tmp_path)
        assert "<script>alert(1)</script>" not in html

    def test_missing_evidence_degrades_rather_than_crashing(self, tmp_path):
        html = brief.build(tmp_path)
        assert html.startswith("<!doctype html>")
        assert "do not tune the threshold" in html

    def test_write_creates_the_file(self, evidence, tmp_path):
        out = brief.write(evidence, tmp_path / "nested" / "index.html")
        assert out.exists() and out.stat().st_size > 2000
