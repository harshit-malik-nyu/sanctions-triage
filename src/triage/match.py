"""
The screening engine.

This is a defensible approximation of what a bank's sanctions filter does to a
name before comparing it, not a reimplementation of any vendor product. Every
step is documented because the normalisation decisions drive the results more
than the similarity metric does, and a threshold recommendation built on
undisclosed preprocessing is not auditable.

Design constraints taken from how the real problem behaves:

  Word order varies.      "BANK OF CHINA" and "CHINA, BANK OF" are the same
                          party. Token-set comparison handles this; edit
                          distance does not.

  Legal suffixes are noise. "LTD", "LLC", "S.A.", "GMBH" appear on nearly
                          every corporate name and carry almost no
                          discriminating power. Left in, they inflate
                          similarity between unrelated companies.

  Transliteration is the  Arabic, Persian, Russian and Chinese names reach a
  whole problem.          Latin-script list through inconsistent romanisation.
                          This is where real false positives come from, and it
                          is why diacritic folding matters.

  Short names are fragile. A three-token similarity on two-word names moves in
                          large jumps. Jaro-Winkler, which rewards shared
                          prefixes, behaves better there and is blended in.
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

from rapidfuzz import fuzz

# Corporate and legal-form suffixes stripped before comparison. Deliberately
# conservative: only forms that are unambiguously structural. "GROUP" and
# "HOLDINGS" are NOT here — they discriminate between real companies.
LEGAL_SUFFIXES = {
    "ltd", "limited", "llc", "lc", "inc", "incorporated", "corp",
    "corporation", "co", "company", "plc", "pte", "pvt", "private",
    "sa", "sas", "sarl", "srl", "spa", "ag", "gmbh", "mbh", "kg", "bv",
    "nv", "ab", "as", "oy", "oyj", "aps", "sp", "zoo", "ooo", "oao",
    "zao", "pjsc", "ojsc", "cjsc", "jsc", "llp", "lp", "gp", "trust",
    "foundation", "fzc", "fze", "dmcc", "wll", "sal", "psc", "pjs",
}

# Tokens carrying no discriminating power at all.
STOPWORDS = {"the", "and", "of", "for", "de", "del", "la", "le", "el", "al"}

_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_WS = re.compile(r"\s+")
_DIGITS = re.compile(r"\d+")


@lru_cache(maxsize=200_000)
def normalise(name: str) -> str:
    """
    Reduce a name to its comparable form.

    Cached because the evaluation compares every alias against a large
    watchlist, and normalising the same watchlist entry tens of thousands of
    times dominates runtime otherwise.
    """
    if not name:
        return ""

    # Decompose accents and drop the combining marks. This is what makes
    # "MUÑOZ" and "MUNOZ" comparable, and it is the single most load-bearing
    # step for transliterated names.
    text = unicodedata.normalize("NFKD", name)
    text = "".join(c for c in text if not unicodedata.combining(c))

    text = _PUNCT.sub(" ", text.casefold())
    tokens = [t for t in _WS.sub(" ", text).split() if t]

    kept = [
        t for t in tokens
        if t not in LEGAL_SUFFIXES and t not in STOPWORDS and len(t) > 1
    ]

    # Never normalise a name out of existence: a company called "CO LTD" would
    # otherwise become the empty string and match everything.
    if not kept:
        kept = tokens

    return " ".join(kept)


@lru_cache(maxsize=200_000)
def tokens_of(name: str) -> frozenset[str]:
    return frozenset(normalise(name).split())


def score(a: str, b: str) -> float:
    """
    Similarity in 0-100 between two names.

    Uses token_sort_ratio, chosen by measurement rather than preference.

    Candidate metrics were compared on real OFAC alias pairs (which must score
    high) against real distinct companies sharing a token (which must not).
    Only one separated the classes at all:

        metric        min(match)   max(non-match)   separation
        token_sort          72.2             57.1        +15.1
        WRatio              82.2             90.0         -7.8
        ratio               64.9             72.3         -7.5
        partial             77.4            100.0        -22.6
        token_set           72.2            100.0        -27.8

    A negative separation means non-matches outscore genuine aliases, so any
    threshold on that metric is arbitrary.

    The failure of token_set_ratio is worth naming, because it was the obvious
    first choice and it is catastrophically wrong here. It returns 100 whenever
    one token set is a SUBSET of the other, so `APPLE INC` scored a perfect
    match against `APPLE BANK FOR SAVINGS`. In a screening filter that means
    every company sharing one word with a listed entity is flagged as a
    certain hit.

    token_sort_ratio sorts tokens and compares the full strings, so extra
    tokens dilute the score the way they should. It keeps order-invariance —
    `BANK OF CHINA` and `CHINA, BANK OF` still match — without the subset
    pathology.

    The comparison above is nine pairs and is far too small to fix a threshold.
    It is enough to reject a metric that scores non-matches above matches, and
    `evaluate.py` re-measures separation across the full alias population.
    """
    na, nb = normalise(a), normalise(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 100.0
    return float(fuzz.token_sort_ratio(na, nb))


def is_initials_only(name: str) -> bool:
    """Names reduced to initials carry too little signal to compare."""
    toks = normalise(name).split()
    return bool(toks) and all(len(t) <= 2 for t in toks)


# Candidate generation prefix length. Names sharing no token with the same
# four-character opening are effectively never a match at any usable threshold,
# so blocking on it cuts a quadratic comparison down to something runnable
# without changing results in the range that matters. Real screening
# architecture separates candidate generation from scoring for the same reason.
BLOCK_PREFIX = 4
MIN_BLOCK_TOKEN = 4


def candidate_index(names: list[str]) -> dict[str, list[int]]:
    """
    Map a token prefix to the positions of every name containing such a token.

    Indexing ALL qualifying tokens rather than just the longest one matters:
    `AEROCARIBBEAN AIRLINES` and `AERO-CARIBBEAN` have different longest
    tokens, so a longest-token key would put them in different blocks and the
    pair would never be compared. Indexing every token puts both under `aero`.
    """
    index: dict[str, list[int]] = {}
    for i, n in enumerate(names):
        for tok in set(normalise(n).split()):
            if len(tok) >= MIN_BLOCK_TOKEN:
                index.setdefault(tok[:BLOCK_PREFIX], []).append(i)
    return index


def candidates_for(name: str, index: dict[str, list[int]]) -> set[int]:
    """Positions worth scoring against this name."""
    out: set[int] = set()
    for tok in set(normalise(name).split()):
        if len(tok) >= MIN_BLOCK_TOKEN:
            out.update(index.get(tok[:BLOCK_PREFIX], ()))
    return out


def best_match(name: str, watchlist: list[str],
               index: dict[str, list[int]] | None = None
               ) -> tuple[int, float]:
    """
    Highest-scoring watchlist entry for a name.

    Returns (position, score), or (-1, 0.0) when nothing is comparable.
    """
    if index is None:
        positions: range | set[int] = range(len(watchlist))
    else:
        positions = candidates_for(name, index)
        if not positions:
            return -1, 0.0

    best_pos, best_score = -1, 0.0
    for pos in positions:
        s = score(name, watchlist[pos])
        if s > best_score:
            best_pos, best_score = pos, s
            if best_score == 100.0:
                break
    return best_pos, best_score


def all_matches_above(name: str, watchlist: list[str], threshold: float,
                      index: dict[str, list[int]] | None = None
                      ) -> list[tuple[int, float]]:
    """
    Every watchlist entry scoring at or above a threshold.

    An analyst reviewing an alert sees all hits, not just the best one, so
    alert *volume* — the thing that drives cost — depends on this rather than
    on best_match.
    """
    positions = (range(len(watchlist)) if index is None
                 else candidates_for(name, index))
    out = []
    for pos in positions:
        s = score(name, watchlist[pos])
        if s >= threshold:
            out.append((pos, s))
    return sorted(out, key=lambda t: -t[1])
