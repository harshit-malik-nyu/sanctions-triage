"""
OFAC sanctions data.

Two files carry this project.

`sdn.csv` is the Specially Designated Nationals list: the watchlist a bank
screens against. Roughly seventeen thousand entries, no header row, nulls
encoded as the literal string `-0-`.

`alt.csv` is the alternate-names file, and it is the reason this project can
exist without inventing data. OFAC publishes real aliases for sanctioned
parties — transliteration variants, abbreviations, former names, trading names.
`AERO-CARIBBEAN` for `AEROCARIBBEAN AIRLINES`. Each alias carries the entity
number of the SDN entry it belongs to.

That linkage is the ground truth. Screening a real alias against the
primary-name list *should* produce a match on that specific entity. When it
does not, a real screening system would have let a real sanctioned party
through — which is a genuine miss, established by OFAC's own published data
rather than by anyone's judgment or by a generator.

Everything here is public domain, published by the U.S. Treasury, and
re-downloadable by any reader who wants to check a number.
"""

from __future__ import annotations

import csv
import io
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

# Treasury publishes these at stable paths. The list-service mirror serves the
# identical bytes and is kept as a fallback rather than a preference.
SDN_URL = "https://www.treasury.gov/ofac/downloads/sdn.csv"
ALT_URL = "https://www.treasury.gov/ofac/downloads/alt.csv"
SDN_MIRROR = ("https://sanctionslistservice.ofac.treas.gov/api/"
              "PublicationPreview/exports/SDN.CSV")
ALT_MIRROR = ("https://sanctionslistservice.ofac.treas.gov/api/"
              "PublicationPreview/exports/ALT.CSV")

USER_AGENT = (
    "sanctions-triage-research/0.1 "
    "(non-commercial research; contact via GitHub issues)"
)

# OFAC encodes an absent field as this literal, not as an empty string.
NULL_TOKEN = "-0-"

# sdn.csv has no header. Column order is fixed and documented by OFAC.
SDN_COLUMNS = [
    "ent_num", "sdn_name", "sdn_type", "program", "title",
    "call_sign", "vess_type", "tonnage", "grt", "vess_flag",
    "vess_owner", "remarks",
]

ALT_COLUMNS = ["ent_num", "alt_num", "alt_type", "alt_name", "alt_remarks"]


class OfacUnavailable(RuntimeError):
    """The list could not be retrieved. Never treated as an empty list."""


def _clean(value: str | None) -> str | None:
    """OFAC nulls are the string '-0-', with trailing whitespace."""
    if value is None:
        return None
    v = value.strip()
    return None if v in ("", NULL_TOKEN) else v


def _fetch(url: str, timeout: int = 120) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    return raw.decode("utf-8", errors="replace")


def fetch_with_fallback(primary: str, mirror: str, label: str) -> str:
    """
    Retrieve a list, trying the mirror if the primary path fails.

    A failure here must not silently become an empty watchlist. Screening
    against nothing produces zero alerts and a perfect-looking false-positive
    rate, which is the most dangerous possible failure mode for this kind of
    tool: it looks like success.
    """
    for url in (primary, mirror):
        try:
            text = _fetch(url)
            if len(text) < 10_000:
                log.warning("%s from %s is implausibly small (%s bytes)",
                            label, url, len(text))
                continue
            log.info("%s: %s bytes from %s", label, len(text), url)
            return text
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
            log.warning("%s unavailable at %s: %s", label, url, exc)

    raise OfacUnavailable(
        f"could not retrieve {label} from either published path. Refusing to "
        "continue: an empty watchlist yields zero alerts and a flawless-looking "
        "false-positive rate, which would be the most misleading result this "
        "project could produce."
    )


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SdnEntry:
    """One primary entry on the SDN list."""

    ent_num: int
    name: str
    sdn_type: str | None          # "individual", "vessel", "aircraft", or None (entity)
    program: str | None
    remarks: str | None = None

    @property
    def is_individual(self) -> bool:
        return (self.sdn_type or "").lower() == "individual"

    @property
    def is_entity(self) -> bool:
        """
        OFAC leaves sdn_type blank for corporate entities.

        That is a genuine encoding quirk rather than missing data, and reading
        blank as unknown would discard the entire entity population — which is
        what a bank screening corporate counterparties cares about most.
        """
        return self.sdn_type is None


@dataclass(frozen=True)
class Alias:
    """
    A published alternate name, linked to the SDN entry it belongs to.

    `ent_num` is the ground truth: screening `name` should match the SDN entry
    carrying this entity number.
    """

    ent_num: int
    alt_num: int
    alt_type: str | None          # "aka", "fka", "nka"
    name: str


@dataclass
class OfacSnapshot:
    entries: list[SdnEntry] = field(default_factory=list)
    aliases: list[Alias] = field(default_factory=list)
    retrieved_utc: str = ""
    sdn_bytes: int = 0
    alt_bytes: int = 0
    sdn_sha256: str = ""
    alt_sha256: str = ""

    def by_ent_num(self) -> dict[int, SdnEntry]:
        return {e.ent_num: e for e in self.entries}

    def entities(self) -> list[SdnEntry]:
        return [e for e in self.entries if e.is_entity]

    def individuals(self) -> list[SdnEntry]:
        return [e for e in self.entries if e.is_individual]

    def aliases_with_target(self) -> list[tuple[Alias, SdnEntry]]:
        """Aliases whose parent entry is present — the usable ground truth."""
        index = self.by_ent_num()
        return [(a, index[a.ent_num]) for a in self.aliases if a.ent_num in index]

    def provenance(self) -> dict:
        return {
            "source": "U.S. Treasury OFAC, public domain",
            "sdn_url": SDN_URL,
            "alt_url": ALT_URL,
            "retrieved_utc": self.retrieved_utc,
            "sdn_bytes": self.sdn_bytes,
            "alt_bytes": self.alt_bytes,
            "sdn_sha256": self.sdn_sha256,
            "alt_sha256": self.alt_sha256,
            "entries": len(self.entries),
            "entities": len(self.entities()),
            "individuals": len(self.individuals()),
            "aliases": len(self.aliases),
            "note": (
                "The SDN list changes several times a week. These hashes "
                "identify the exact edition every figure in this study was "
                "computed against; a reader re-running later will get a "
                "different hash and should expect slightly different counts."
            ),
        }


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_sdn(text: str) -> list[SdnEntry]:
    out: list[SdnEntry] = []
    reader = csv.reader(io.StringIO(text))
    for row in reader:
        if len(row) < 4:
            continue
        rec = dict(zip(SDN_COLUMNS, row))
        try:
            ent = int(str(rec["ent_num"]).strip())
        except (ValueError, TypeError):
            continue
        name = _clean(rec.get("sdn_name"))
        if not name:
            continue
        out.append(SdnEntry(
            ent_num=ent,
            name=name,
            sdn_type=_clean(rec.get("sdn_type")),
            program=_clean(rec.get("program")),
            remarks=_clean(rec.get("remarks")),
        ))
    return out


def parse_alt(text: str) -> list[Alias]:
    out: list[Alias] = []
    reader = csv.reader(io.StringIO(text))
    for row in reader:
        if len(row) < 4:
            continue
        rec = dict(zip(ALT_COLUMNS, row))
        try:
            ent = int(str(rec["ent_num"]).strip())
            alt = int(str(rec["alt_num"]).strip())
        except (ValueError, TypeError):
            continue
        name = _clean(rec.get("alt_name"))
        if not name:
            continue
        out.append(Alias(
            ent_num=ent, alt_num=alt,
            alt_type=_clean(rec.get("alt_type")), name=name,
        ))
    return out


def load(cache_dir: str | Path | None = None) -> OfacSnapshot:
    """Retrieve and parse both lists, recording provenance."""
    import hashlib

    cache = Path(cache_dir) if cache_dir else None
    if cache:
        cache.mkdir(parents=True, exist_ok=True)

    def get(primary: str, mirror: str, label: str, filename: str) -> str:
        if cache and (cache / filename).exists():
            log.info("%s: using cached copy", label)
            return (cache / filename).read_text(encoding="utf-8")
        text = fetch_with_fallback(primary, mirror, label)
        if cache:
            (cache / filename).write_text(text, encoding="utf-8")
        return text

    sdn_text = get(SDN_URL, SDN_MIRROR, "SDN list", "sdn.csv")
    alt_text = get(ALT_URL, ALT_MIRROR, "alternate names", "alt.csv")

    snapshot = OfacSnapshot(
        entries=parse_sdn(sdn_text),
        aliases=parse_alt(alt_text),
        retrieved_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        sdn_bytes=len(sdn_text.encode()),
        alt_bytes=len(alt_text.encode()),
        sdn_sha256=hashlib.sha256(sdn_text.encode()).hexdigest(),
        alt_sha256=hashlib.sha256(alt_text.encode()).hexdigest(),
    )

    if len(snapshot.entries) < 1000:
        raise OfacUnavailable(
            f"parsed only {len(snapshot.entries)} SDN entries, which is far "
            "below the published list size. The format has probably changed; "
            "refusing to report results from a truncated watchlist."
        )

    log.info("OFAC: %s entries (%s entities, %s individuals), %s aliases",
             len(snapshot.entries), len(snapshot.entities()),
             len(snapshot.individuals()), len(snapshot.aliases))
    return snapshot
