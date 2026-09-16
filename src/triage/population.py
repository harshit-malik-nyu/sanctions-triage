"""
The population being screened.

A screening filter is measured against two things: sanctioned parties it must
catch, and everyone else it must leave alone. The second group is the harder
one to obtain honestly, because the obvious move — generating plausible company
names — puts invented data at the centre of the false-positive rate, which is
the number the whole analysis turns on.

So the population here is real registered legal entities from public
registries. SEC EDGAR's company file lists every issuer filing with the
Commission; GLEIF publishes the global Legal Entity Identifier register. Both
are public record, both are organisations rather than private individuals, and
neither was assembled by me.

Ground truth by construction
----------------------------
A company registered with the SEC and filing quarterly is not a sanctioned
party. That claim is checked rather than assumed: `find_overlaps` runs an exact
normalised match against the SDN list before anything else, and any genuine
collision is removed from the negative set and reported. Treating a real
sanctioned entity as a false positive would corrupt the headline rate in the
flattering direction.

Why entities and not individuals
--------------------------------
Real personal names are obtainable, and using them would be a privacy problem
this project does not need. Screening a real person's name against a sanctions
list and publishing the near-misses would put named private individuals in a
public repository next to the word "sanctions". Corporate names carry no such
exposure, and entity screening is most of what a corporate bank actually does.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

# SEC requires a User-Agent naming the requester and a contact address.
# A generic agent is refused with HTTP 403 — measured, not assumed.
SEC_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_UA = ("sanctions-triage-research "
          "harshit-malik-nyu@users.noreply.github.com")

GLEIF_URL = "https://api.gleif.org/api/v1/lei-records"
GLEIF_UA = "sanctions-triage-research/0.1"


class PopulationUnavailable(RuntimeError):
    """No clean population could be retrieved. Never silently empty."""


@dataclass
class Entity:
    name: str
    identifier: str
    source: str
    country: str | None = None


@dataclass
class Population:
    entities: list[Entity] = field(default_factory=list)
    source: str = ""
    retrieved_utc: str = ""
    removed_overlaps: list[str] = field(default_factory=list)

    def names(self) -> list[str]:
        return [e.name for e in self.entities]

    def provenance(self) -> dict:
        return {
            "source": self.source,
            "retrieved_utc": self.retrieved_utc,
            "count": len(self.entities),
            "removed_sanctioned_overlaps": len(self.removed_overlaps),
            "overlap_names": self.removed_overlaps[:20],
            "note": (
                "Real registered legal entities from a public registry. "
                "Entities exactly matching an SDN entry were removed from the "
                "negative set and are listed here, because counting a genuine "
                "sanctioned party as a false positive would flatter the "
                "headline rate."
            ),
        }


def _get(url: str, ua: str, timeout: int = 90) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": ua})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def fetch_sec(limit: int | None = None) -> list[Entity]:
    """
    Every company filing with the SEC.

    The file is a JSON object keyed by row index rather than a list, which is a
    quirk of the endpoint rather than of the data.
    """
    raw = _get(SEC_URL, SEC_UA)
    data = json.loads(raw.decode("utf-8", errors="replace"))

    rows = data.values() if isinstance(data, dict) else data
    out: list[Entity] = []
    for row in rows:
        title = (row.get("title") or "").strip()
        if not title:
            continue
        out.append(Entity(
            name=title,
            identifier=f"CIK{row.get('cik_str')}",
            source="SEC EDGAR",
            country="US",
        ))
        if limit and len(out) >= limit:
            break
    return out


def fetch_gleif(limit: int = 5000, page_size: int = 200) -> list[Entity]:
    """
    Legal entities from the global LEI register.

    Broader than EDGAR and not US-centric, which matters: transliterated
    non-English names are where sanctions screening actually generates its
    false positives, and a purely US population would understate that.
    """
    out: list[Entity] = []
    page = 1

    while len(out) < limit and page <= 200:
        url = (f"{GLEIF_URL}?page[size]={min(page_size, 200)}&page[number]={page}")
        try:
            data = json.loads(_get(url, GLEIF_UA).decode("utf-8", errors="replace"))
        except (urllib.error.URLError, urllib.error.HTTPError,
                json.JSONDecodeError, OSError) as exc:
            log.warning("GLEIF page %s failed: %s", page, exc)
            break

        records = data.get("data") or []
        if not records:
            break

        for rec in records:
            attrs = (rec.get("attributes") or {})
            ent = (attrs.get("entity") or {})
            name = ((ent.get("legalName") or {}).get("name") or "").strip()
            if not name:
                continue
            country = ((ent.get("legalAddress") or {}).get("country"))
            out.append(Entity(
                name=name,
                identifier=attrs.get("lei") or rec.get("id") or "",
                source="GLEIF LEI",
                country=country,
            ))
            if len(out) >= limit:
                break
        page += 1

    return out


def find_overlaps(names: list[str], sdn_names: list[str]) -> set[str]:
    """
    Population entries that exactly match an SDN entry after normalisation.

    Exact normalised equality only. A fuzzy check here would remove the very
    near-misses the study is trying to count, quietly deleting the hardest
    false positives and improving the result by construction.
    """
    from .match import normalise

    sdn_norm = {normalise(n) for n in sdn_names if n}
    return {n for n in names if normalise(n) in sdn_norm}


def load(sdn_names: list[str], *, limit: int = 8000,
         cache_dir: str | Path | None = None,
         prefer: str = "sec") -> Population:
    """
    Retrieve a clean population, trying sources in order and recording which
    one answered.
    """
    cache = Path(cache_dir) if cache_dir else None
    if cache:
        cache.mkdir(parents=True, exist_ok=True)
        cached = cache / "population.json"
        if cached.exists():
            payload = json.loads(cached.read_text())
            log.info("population: using cached copy (%s)", payload["source"])
            pop = Population(
                entities=[Entity(**e) for e in payload["entities"]],
                source=payload["source"],
                retrieved_utc=payload["retrieved_utc"],
            )
            return _strip_overlaps(pop, sdn_names)

    attempts = [("SEC EDGAR", lambda: fetch_sec(limit)),
                ("GLEIF LEI", lambda: fetch_gleif(limit))]
    if prefer == "gleif":
        attempts.reverse()

    for label, fn in attempts:
        try:
            entities = fn()
        except (urllib.error.URLError, urllib.error.HTTPError,
                json.JSONDecodeError, OSError) as exc:
            log.warning("%s unavailable: %s", label, exc)
            continue

        if len(entities) < 500:
            log.warning("%s returned only %s entities; trying the next source",
                        label, len(entities))
            continue

        pop = Population(
            entities=entities, source=label,
            retrieved_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        log.info("population: %s entities from %s", len(entities), label)

        if cache:
            (cache / "population.json").write_text(json.dumps({
                "source": pop.source,
                "retrieved_utc": pop.retrieved_utc,
                "entities": [e.__dict__ for e in pop.entities],
            }))

        return _strip_overlaps(pop, sdn_names)

    raise PopulationUnavailable(
        "no public registry returned a usable entity population. Refusing to "
        "continue: the false-positive rate is measured against this set, and "
        "substituting generated names would put invented data at the centre of "
        "the headline number."
    )


def _strip_overlaps(pop: Population, sdn_names: list[str]) -> Population:
    overlaps = find_overlaps(pop.names(), sdn_names)
    if overlaps:
        log.warning("removing %s population entries that exactly match an SDN "
                    "entry: %s", len(overlaps), sorted(overlaps)[:5])
        pop.entities = [e for e in pop.entities if e.name not in overlaps]
        pop.removed_overlaps = sorted(overlaps)
    return pop
