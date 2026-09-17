"""
Entity resolution across SDN listings.

OFAC lists the same organisation under several entity numbers. A group can be
designated separately by country, by sanctions programme, or on different
dates, and each designation gets its own `ent_num`. `AL-AQSA ISLAMIC CHARITABLE
SOCIETY` and `ISLAMIC CHARITABLE SOCIETY FOR AL-AQSA` are two listings of one
organisation; so are `POPULAR REVOLUTIONARY STRUGGLE` and `REVOLUTIONARY
POPULAR STRUGGLE`.

Why this module exists
----------------------
The first measurement scored recall by requiring the matched entity number to
equal the true one. Under that rule a held-out alias that matched its own
organisation's sister listing at a score of 100 was recorded as a miss — and
1,759 of 2,860 apparent failures were exactly that.

Reported recall was 52.3%. Most of the gap was the measurement, not the filter.

An analyst reviewing either listing sees a designated party and blocks. Calling
that a miss understates the filter by a wide margin; but counting any hit on
any sanctioned party as a success would overstate attribution, since matching
an unrelated designated entity is a different event. Clustering separates the
two properly: a hit inside the true organisation's cluster is a catch, a hit
outside it is not.

Method
------
Union-find over the watchlist. Two entries are merged when any of their
published names — primary or alias — match above a deliberately high threshold.
The threshold is high on purpose: merging two genuinely distinct organisations
would inflate recall by making misses look like catches, which is the error
that flatters the result.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field

from .match import candidate_index, candidates_for, score

log = logging.getLogger(__name__)

# Two listings are treated as one organisation only at near-identity.
#
# Set high because the failure modes are asymmetric. Merging distinct
# organisations converts genuine misses into apparent catches and inflates
# recall — the flattering direction. Failing to merge true duplicates leaves
# recall understated, which is the safe error. 95 was chosen to admit word-order
# variants and punctuation differences while rejecting shared-theme names like
# `AL-AQSA FOUNDATION` versus `AL-AQSA ISLAMIC CHARITABLE SOCIETY`, which are
# related but separately designated.
SAME_ORG_THRESHOLD = 95.0


class UnionFind:
    def __init__(self) -> None:
        self.parent: dict[int, int] = {}

    def find(self, x: int) -> int:
        self.parent.setdefault(x, x)
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:          # path compression
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


@dataclass
class Clustering:
    cluster_of: dict[int, int] = field(default_factory=dict)
    members: dict[int, set[int]] = field(default_factory=dict)
    merged_examples: list[tuple[str, str]] = field(default_factory=list)

    def same_org(self, a: int | None, b: int | None) -> bool:
        if a is None or b is None:
            return False
        return self.cluster_of.get(a, a) == self.cluster_of.get(b, b)

    def summary(self) -> dict:
        sizes = [len(m) for m in self.members.values()]
        multi = [s for s in sizes if s > 1]
        return {
            "entities": len(self.cluster_of),
            "clusters": len(self.members),
            "multi_listing_clusters": len(multi),
            "entities_in_multi_listing_clusters": sum(multi),
            "largest_cluster": max(sizes) if sizes else 0,
            "threshold": SAME_ORG_THRESHOLD,
            "examples": self.merged_examples[:15],
            "note": (
                "OFAC designates the same organisation more than once — by "
                "country, by programme, by date — and each designation carries "
                "its own entity number. Requiring exact entity-number equality "
                "counted a perfect match against a sister listing as a miss, "
                "which accounted for most of an apparent 52% recall."
            ),
        }


def build(watchlist) -> Clustering:
    """
    Cluster watchlist entries that describe the same organisation.

    Candidate generation reuses the screening index, so this is roughly linear
    in watchlist size rather than quadratic.
    """
    names = [w.name for w in watchlist]
    ents = [w.ent_num for w in watchlist]
    index = candidate_index(names)

    uf = UnionFind()
    for e in ents:
        uf.find(e)

    examples: list[tuple[str, str]] = []
    seen_pairs: set[tuple[int, int]] = set()

    for i, name in enumerate(names):
        for j in candidates_for(name, index):
            if j <= i:
                continue
            if ents[i] == ents[j]:
                continue
            key = (min(ents[i], ents[j]), max(ents[i], ents[j]))
            if key in seen_pairs:
                continue
            if score(name, names[j]) >= SAME_ORG_THRESHOLD:
                seen_pairs.add(key)
                uf.union(ents[i], ents[j])
                if len(examples) < 40:
                    examples.append((name, names[j]))

    cluster_of = {e: uf.find(e) for e in set(ents)}
    members: dict[int, set[int]] = defaultdict(set)
    for e, root in cluster_of.items():
        members[root].add(e)

    clustering = Clustering(
        cluster_of=cluster_of, members=dict(members), merged_examples=examples)
    s = clustering.summary()
    log.info("entity resolution: %s listings -> %s organisations "
             "(%s multi-listing)", s["entities"], s["clusters"],
             s["multi_listing_clusters"])
    return clustering


def unreachable_aliases(alias_results) -> list:
    """
    Aliases that generated no candidate at any threshold.

    These are the genuine floor on name-only screening. `COIBA`, `ALEPH`,
    `EKIN`, `XAKI` — acronyms and unrelated trading names that share no
    character sequence with any other published name for the same party. No
    similarity metric and no threshold reaches them, because there is nothing
    to be similar to.

    Catching them requires a different signal entirely: date of birth,
    registration number, address, or the listing identifier itself. That is a
    finding about the limits of name screening rather than about this
    implementation, and it is the strongest argument in the report for
    investing in secondary identifiers rather than in better fuzzy matching.
    """
    return [r for r in alias_results if r.hit_score == 0.0]
