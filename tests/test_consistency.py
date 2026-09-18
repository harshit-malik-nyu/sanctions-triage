"""
Consistency between the README and the committed evidence.

A figure quoted in prose drifts from the figure the code produces. It happened
here: the README carried 15.1% and 75.9% while the individual comparison, the
population-tuning result and the regulator benchmark — the three strongest
findings — existed only in JSON.

Nobody reads JSON. The document people read is where a stale number does its
damage, so the agreement is asserted rather than trusted.

These tests skip rather than fail when evidence is absent, because a fresh
clone has no committed run and a red suite on a clean checkout teaches people
to ignore the suite.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence"
README = ROOT / "README.md"


def _load(name: str):
    p = EVIDENCE / name
    if not p.exists():
        pytest.skip(f"no committed evidence at {p}")
    return json.loads(p.read_text())


def _readme() -> str:
    if not README.exists():
        pytest.skip("no README")
    return README.read_text()


def _quoted_percentages(text: str) -> set[str]:
    return set(re.findall(r"\b\d{1,2}\.\d%", text))


class TestReadmeMatchesEvidence:

    def test_unreachable_share_is_current(self):
        """The figure the entire recommendation rests on."""
        prov = _load("provenance.json")
        share = (prov.get("unreachable_aliases") or {}).get("share")
        if share is None:
            pytest.skip("no unreachable figure in evidence")
        assert f"{share:.1%}" in _readme(), (
            f"README does not quote the current unreachable share {share:.1%}")

    def test_best_recall_is_current(self):
        sweep = _load("sweep.json")
        best = max(p.get("recall", 0) for p in sweep)
        assert f"{best:.1%}" in _readme(), (
            f"README does not quote the current best recall {best:.1%}")

    def test_individual_comparison_is_quoted(self):
        """
        The measured answer to the strongest objection. It existed only in
        JSON while the README still described the objection as open.
        """
        prov = _load("provenance.json")
        ind = prov.get("individuals_comparison") or {}
        rate = ind.get("unreachable_rate")
        if rate is None:
            pytest.skip("individual comparison not in evidence")
        assert f"{rate:.1%}" in _readme()

    def test_population_tuning_loss_is_quoted(self):
        prov = _load("provenance.json")
        tuning = ((prov.get("operational_levers") or {})
                  .get("population_tuning") or {})
        loss = tuning.get("recall_lost_to_a_single_threshold")
        if loss is None:
            pytest.skip("population tuning not in evidence")
        assert f"{loss:.1%}" in _readme()

    def test_no_stale_percentages_in_the_recommendation_block(self):
        """
        Every percentage in the recommendation section must appear somewhere in
        the evidence. A number in prose that the code no longer produces is the
        exact failure this project exists to detect, one level up.
        """
        readme = _readme()
        start = readme.find("## Recommendation")
        end = readme.find("## What a false positive")
        if start < 0 or end < 0:
            pytest.skip("recommendation section not found")

        quoted = _quoted_percentages(readme[start:end])
        if not quoted:
            pytest.skip("no percentages quoted")

        blob = json.dumps([_load("provenance.json"), _load("sweep.json"),
                           _load("recommendation.json")])
        available = set()
        for m in re.finditer(r"0\.\d+", blob):
            available.add(f"{float(m.group(0)):.1%}")

        stale = {q for q in quoted if q not in available}
        assert not stale, f"README quotes figures absent from evidence: {stale}"


class TestEvidenceIntegrity:

    def test_provenance_records_the_exact_list_edition(self):
        """
        The SDN list changes several times a week. Without a hash, no figure
        here can be tied to the data that produced it.
        """
        ofac = _load("provenance.json").get("ofac", {})
        assert len(ofac.get("sdn_sha256", "")) == 64
        assert ofac.get("retrieved_utc")

    def test_population_overlaps_were_removed(self):
        """
        Counting a genuine sanctioned party as a false positive would flatter
        the headline in the convenient direction.
        """
        pop = _load("provenance.json").get("population", {})
        assert "removed_sanctioned_overlaps" in pop

    def test_sweep_recall_is_monotonic(self):
        sweep = _load("sweep.json")
        ordered = sorted(sweep, key=lambda p: p["threshold"])
        recalls = [p["recall"] for p in ordered]
        assert recalls == sorted(recalls, reverse=True)

    def test_unstable_assumptions_are_named(self):
        """
        Four of five assumptions move the optimum. Reporting which is the
        honest alternative to quoting a midpoint.
        """
        rec = _load("recommendation.json")
        assert "unstable_under" in rec or "sensitivities" in rec
