"""
Screening engine tests.

Most of these exist because the case they pin was a real failure found by
reading individual results rather than by looking at a rate. Name matching is
unusually prone to that: the aggregate looks reasonable while specific pairs
are catastrophically wrong.
"""

from __future__ import annotations

import pytest

from triage.match import (
    LEGAL_SUFFIXES, candidate_index, candidates_for, normalise, score,
)


class TestNormalisation:

    def test_case_and_punctuation_folded(self):
        assert normalise("Aero-Caribbean!") == "aero caribbean"

    def test_diacritics_folded(self):
        """
        The single most load-bearing step for transliterated names, which is
        where sanctions false positives actually come from.
        """
        assert normalise("MUÑOZ") == normalise("MUNOZ")
        assert normalise("Škoda") == normalise("Skoda")

    def test_structural_legal_suffixes_stripped(self):
        assert normalise("CUBANACAN SA") == "cubanacan"
        assert normalise("ACME LIMITED") == "acme"

    def test_dotted_legal_forms_recognised(self):
        """
        REGRESSION. Splitting on periods first turned "S.A." into two single
        letters, the legal form stopped being recognisable, and
        `CUBANACAN, S.A.` lost its match against `CUBANACAN SA`.
        """
        assert normalise("CUBANACAN, S.A.") == normalise("CUBANACAN SA")
        assert normalise("MARS INVESTMENT L.L.C") == "mars investment"

    def test_substantive_words_are_not_stripped(self):
        """
        REGRESSION. "foundation" and "trust" were in the suffix list. For a
        charity the word IS the name, and stripping it made
        `FOUNDATION FOR CONSTRUCTION` normalise to "construction".
        """
        for word in ("foundation", "trust", "group", "holdings", "bank",
                     "international"):
            assert word not in LEGAL_SUFFIXES
        assert "foundation" in normalise("FOUNDATION FOR CONSTRUCTION")

    def test_single_character_tokens_kept(self):
        """
        REGRESSION. Dropping them merged every firm sharing one substantive
        word: `J D CONSTRUCTION` and `R K CONSTRUCTION` both became
        "construction".
        """
        assert normalise("J D CONSTRUCTION") != normalise("R K CONSTRUCTION")
        assert "j" in normalise("J D CONSTRUCTION").split()

    def test_a_name_is_never_normalised_out_of_existence(self):
        """A company literally called "CO LTD" must not become the empty
        string, which would match everything."""
        assert normalise("CO LTD") != ""

    def test_empty_input_is_safe(self):
        assert normalise("") == ""
        assert normalise(None) == ""


class TestScoring:

    REAL_ALIASES = [
        ("AEROCARIBBEAN AIRLINES", "AERO-CARIBBEAN"),
        ("BANCO NACIONAL DE CUBA", "NATIONAL BANK OF CUBA"),
        ("CUBANACAN, S.A.", "CUBANACAN SA"),
        ("HAVANA INTERNATIONAL BANK LTD", "HAVANA INTERNATIONAL BANK"),
    ]

    DISTINCT_COMPANIES = [
        ("APPLE INC", "APPLE BANK FOR SAVINGS"),
        ("BANK OF CHINA", "BANK OF AMERICA"),
        ("DELTA AIR LINES", "DELTA APPAREL"),
        ("J D CONSTRUCTION", "FOUNDATION FOR CONSTRUCTION"),
        ("R K CONSTRUCTION", "FOUNDATION FOR CONSTRUCTION"),
    ]

    @pytest.mark.parametrize("a,b", REAL_ALIASES)
    def test_real_aliases_score_high(self, a, b):
        assert score(a, b) >= 70

    @pytest.mark.parametrize("a,b", DISTINCT_COMPANIES)
    def test_distinct_companies_score_lower(self, a, b):
        assert score(a, b) < 75

    def test_the_classes_are_separated(self):
        """
        The property that makes any threshold meaningful. Without separation,
        a recommended number is arbitrary.
        """
        lo = min(score(a, b) for a, b in self.REAL_ALIASES)
        hi = max(score(a, b) for a, b in self.DISTINCT_COMPANIES)
        assert lo > hi, f"aliases bottom at {lo}, non-matches top at {hi}"

    def test_subset_names_do_not_score_perfect(self):
        """
        REGRESSION, and the most important test here. token_set_ratio returns
        100 whenever one token set is a subset of the other, so `APPLE INC`
        scored a perfect match against `APPLE BANK FOR SAVINGS`. In production
        that flags every company sharing a word with a listed entity as a
        certain hit.
        """
        assert score("APPLE INC", "APPLE BANK FOR SAVINGS") < 60

    def test_word_order_does_not_matter(self):
        assert score("BANK OF CHINA", "CHINA, BANK OF") >= 95

    def test_identical_names_score_100(self):
        assert score("ACME TRADING LTD", "Acme Trading Limited") == 100.0

    def test_empty_names_score_zero(self):
        assert score("", "ACME") == 0.0


class TestBlocking:

    def test_index_covers_every_qualifying_token(self):
        """
        REGRESSION-adjacent. Indexing only the longest token would put
        `AEROCARIBBEAN AIRLINES` under "aero" and `AERO-CARIBBEAN` under
        "cari", so the pair would never be compared at any threshold.
        """
        names = ["AEROCARIBBEAN AIRLINES", "SOMETHING ELSE ENTIRELY"]
        idx = candidate_index(names)
        assert 0 in candidates_for("AERO-CARIBBEAN", idx)

    def test_unrelated_name_generates_no_candidates(self):
        idx = candidate_index(["AEROCARIBBEAN AIRLINES"])
        assert candidates_for("ZZZZQQQQ WIDGETS", idx) == set()

    def test_blocking_does_not_drop_a_genuine_match(self):
        names = ["BANCO NACIONAL DE CUBA", "UNRELATED HOLDINGS"]
        idx = candidate_index(names)
        assert 0 in candidates_for("NATIONAL BANK OF CUBA", idx)
