"""
The brief.

Everything else in this project is a measurement. This is the thing someone
opens.

Written as a threshold-committee paper rather than a report of findings: the
decision first, the number that drives it second, the evidence under that, and
the reasons not to believe it at the bottom where a reader can still find them.
Anything a committee would ask in the first five minutes is above the fold.

Self-contained HTML with no external assets, because a compliance officer opens
it from an email attachment on a locked-down desktop and anything fetching a
remote stylesheet renders as a broken page.
"""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CSS = """
:root{--bg:#fbfbfa;--fg:#1a1a19;--mut:#6b6b68;--line:#e2e2df;--card:#fff;
--bad:#b3261e;--warn:#8a6d00;--ok:#1a7f37;--accent:#1a4d8f}
@media(prefers-color-scheme:dark){:root{--bg:#141413;--fg:#f0efea;--mut:#9a9a94;
--line:#2c2c29;--card:#1c1c1a;--bad:#ff6b5e;--warn:#e0b341;--ok:#4ac26b;
--accent:#6fa8dc}}
*{box-sizing:border-box}
body{margin:0;padding:2.5rem 1.25rem 4rem;background:var(--bg);color:var(--fg);
font:16px/1.65 ui-sans-serif,-apple-system,"Segoe UI",system-ui,sans-serif}
.wrap{max-width:54rem;margin:0 auto}
.eyebrow{font-size:.75rem;letter-spacing:.12em;text-transform:uppercase;
color:var(--mut);margin-bottom:.5rem}
h1{font-size:1.9rem;line-height:1.2;margin:0 0 .4rem;letter-spacing:-.02em}
.sub{color:var(--mut);margin-bottom:2rem;font-size:.95rem}
.decision{background:var(--card);border:1px solid var(--line);
border-left:4px solid var(--accent);border-radius:10px;padding:1.4rem 1.5rem;
margin-bottom:2rem}
.decision h2{margin:0 0 .6rem;font-size:1.3rem;letter-spacing:-.01em}
.decision p{margin:.5rem 0 0}
h2{font-size:1.05rem;margin:2.4rem 0 .9rem;text-transform:uppercase;
letter-spacing:.07em;color:var(--mut);font-weight:620}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(9rem,1fr));
gap:.7rem;margin-bottom:1.4rem}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;
padding:.9rem 1rem}
.card .n{font-size:1.75rem;font-weight:640;letter-spacing:-.03em;
line-height:1.1}
.card .l{font-size:.72rem;color:var(--mut);text-transform:uppercase;
letter-spacing:.06em;margin-top:.25rem}
.card.bad .n{color:var(--bad)}.card.warn .n{color:var(--warn)}
.card.ok .n{color:var(--ok)}
table{width:100%;border-collapse:collapse;margin:.6rem 0 1.2rem;font-size:.9rem}
th,td{text-align:left;padding:.5rem .6rem;border-bottom:1px solid var(--line)}
th{font-size:.72rem;text-transform:uppercase;letter-spacing:.06em;
color:var(--mut);font-weight:620}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.note{background:var(--card);border:1px solid var(--line);border-radius:10px;
padding:1rem 1.1rem;font-size:.9rem;color:var(--mut);margin:1rem 0}
.note strong{color:var(--fg)}
code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.85em}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.82rem}
footer{margin-top:3rem;padding-top:1.2rem;border-top:1px solid var(--line);
color:var(--mut);font-size:.82rem}
a{color:inherit}
"""


def _card(value: str, label: str, cls: str = "") -> str:
    return (f'<div class="card {cls}"><div class="n">{html.escape(value)}</div>'
            f'<div class="l">{html.escape(label)}</div></div>')


def _pct(x: Any, digits: int = 1) -> str:
    try:
        return f"{float(x):.{digits}%}"
    except (TypeError, ValueError):
        return "n/a"


def _usd(x: Any) -> str:
    try:
        return f"${float(x):,.0f}"
    except (TypeError, ValueError):
        return "n/a"


def build(evidence_dir: str | Path) -> str:
    """Assemble the brief from committed evidence."""
    d = Path(evidence_dir)

    def load(name: str) -> Any:
        p = d / name
        return json.loads(p.read_text()) if p.exists() else {}

    prov = load("provenance.json")
    rec = load("recommendation.json")
    sweep = load("sweep.json")

    ofac = prov.get("ofac", {})
    unreachable = prov.get("unreachable_aliases", {})
    individuals = prov.get("individuals_comparison", {})
    levers = prov.get("operational_levers", {})
    benchmark = prov.get("benchmark_check", {})
    fps = rec.get("worst_false_positives", [])
    tuning = (levers or {}).get("population_tuning") or {}
    concentration = (levers or {}).get("list_concentration") or {}
    whitelist = (levers or {}).get("whitelist_impact") or []

    best_recall = max((p.get("recall", 0) for p in sweep), default=0)

    parts: list[str] = []
    parts.append(
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Sanctions screening threshold — decision brief</title>'
        f'<style>{CSS}</style></head><body><div class="wrap">'
    )

    parts.append('<div class="eyebrow">Decision brief</div>')
    parts.append("<h1>Where to set the sanctions screening threshold</h1>")
    parts.append(
        f'<div class="sub">Built on OFAC SDN list edition '
        f'<span class="mono">{html.escape(str(ofac.get("sdn_sha256", ""))[:12])}</span>, '
        f'retrieved {html.escape(str(ofac.get("retrieved_utc", "")))}. '
        f'{ofac.get("entries", 0):,} listings, {ofac.get("aliases", 0):,} published aliases.</div>'
    )

    # ---- the decision ----------------------------------------------------
    parts.append('<div class="decision">')
    parts.append("<h2>Recommendation: do not tune the threshold</h2>")
    parts.append(
        "<p>Entity name screening cannot be made both staffable and adequately "
        "sensitive at any cut-off. The binding constraint is not where the line "
        f"sits — it is that <strong>{_pct(unreachable.get('share', 0))} of published "
        "aliases share no character sequence with any other name for the same "
        "party</strong>, and no similarity metric reaches them.</p>"
        "<p>Investment should go to secondary identifiers — registration number, "
        "date of birth, address — which address that floor. Better fuzzy "
        "matching only moves along a frontier that is already capped.</p>"
    )
    parts.append("</div>")

    parts.append('<div class="cards">')
    parts.append(_card(_pct(best_recall), "best recall, any threshold", "warn"))
    parts.append(_card(_pct(benchmark.get("recall_within_industry_alert_rate", 0)),
                       "recall at a staffable alert rate", "bad"))
    parts.append(_card(_pct(unreachable.get("share", 0)),
                       "unreachable at any threshold", "bad"))
    parts.append(_card(_pct(tuning.get("recall_lost_to_a_single_threshold", 0)),
                       "recall lost to one threshold", "warn"))
    parts.append("</div>")

    # ---- what a false positive looks like ---------------------------------
    if fps:
        parts.append("<h2>What an analyst actually sees</h2>")
        parts.append(
            '<div class="note">Real registered companies matched against real '
            "designated entities, at scores a production filter alerts on. "
            "<strong>IRISL</strong> is the Islamic Republic of Iran Shipping "
            "Lines; <strong>IRIS Marine Services</strong> is an unrelated "
            "Indian company. One character separates them.</div>"
        )
        parts.append("<table><tr><th class='num'>Score</th><th>Screened party</th>"
                     "<th>Designated entity</th></tr>")
        for f in fps[:6]:
            parts.append(
                f"<tr><td class='num'>{float(f.get('score', 0)):.1f}</td>"
                f"<td>{html.escape(str(f.get('company', ''))[:48])}</td>"
                f"<td>{html.escape(str(f.get('matched_sdn_name', ''))[:48])}</td></tr>"
            )
        parts.append("</table>")

    # ---- the frontier ------------------------------------------------------
    if sweep:
        parts.append("<h2>The trade-off</h2>")
        parts.append("<table><tr><th class='num'>Threshold</th>"
                     "<th class='num'>Recall</th><th class='num'>Alert rate</th>"
                     "<th class='num'>Alerts per 10k</th></tr>")
        for p in sweep:
            if int(p.get("threshold", 0)) % 6:
                continue
            parts.append(
                f"<tr><td class='num'>{p['threshold']:.0f}</td>"
                f"<td class='num'>{_pct(p.get('recall'))}</td>"
                f"<td class='num'>{_pct(p.get('false_positive_rate'), 2)}</td>"
                f"<td class='num'>{p.get('alerts_per_10k_screened', 0):,.0f}</td></tr>"
            )
        parts.append("</table>")
        parts.append(
            '<div class="note">No row is acceptable. High recall needs an alert '
            "rate no institution can staff; a staffable alert rate clears well "
            "under half of unseen variants. <strong>That is the finding, not a "
            "failure to produce a number.</strong></div>"
        )

    # ---- levers that do not move the threshold -----------------------------
    parts.append("<h2>What to do instead</h2>")

    if whitelist:
        parts.append("<p><strong>Maintain a false-hit list.</strong> OFAC "
                     "explicitly recognises suppressing alerts from reviewed "
                     "non-matches. A party alerting today alerts every month "
                     "after, so the saving recurs.</p>")
        parts.append("<table><tr><th class='num'>Parties suppressed</th>"
                     "<th class='num'>Alert volume removed</th></tr>")
        for w in whitelist:
            parts.append(
                f"<tr><td class='num'>{w.get('whitelisted_parties', 0):,}</td>"
                f"<td class='num'>{_pct(w.get('volume_reduction'))}</td></tr>")
        parts.append("</table>")

    if tuning:
        ent = tuning.get("entity", {})
        ind = tuning.get("individual", {})
        parts.append(
            "<p><strong>Run separate thresholds by population.</strong> Entity "
            "and personal names fail differently, and one threshold across both "
            "serves neither.</p>"
        )
        parts.append("<table><tr><th>Population</th><th class='num'>Threshold</th>"
                     "<th class='num'>Recall</th><th class='num'>Unreachable</th></tr>")
        parts.append(
            f"<tr><td>Entities</td><td class='num'>{ent.get('threshold', 0):.0f}</td>"
            f"<td class='num'>{_pct(ent.get('recall'))}</td>"
            f"<td class='num'>{_pct(ent.get('unreachable_rate'))}</td></tr>")
        parts.append(
            f"<tr><td>Individuals</td><td class='num'>{ind.get('threshold', 0):.0f}</td>"
            f"<td class='num'>{_pct(ind.get('recall'))}</td>"
            f"<td class='num'>{_pct(ind.get('unreachable_rate'))}</td></tr>")
        parts.append("</table>")
        parts.append(
            f'<div class="note">Using a single threshold costs '
            f'<strong>{_pct(tuning.get("recall_lost_to_a_single_threshold"))}</strong> '
            "of recall — given up for administrative convenience rather than for "
            "a reason.</div>"
        )

    if concentration:
        parts.append(
            f"<p><strong>Fix the worst list entries.</strong> "
            f"{_pct(concentration.get('top_5pct_share_of_alerts'))} of alerts come "
            f"from the worst 5% of entries. Tightening those is cheaper than a "
            f"global threshold move that degrades recall against every other "
            f"entry on the list.</p>"
        )
        worst = concentration.get("worst_entries", [])[:5]
        if worst:
            parts.append("<table><tr><th class='num'>Alerts</th>"
                         "<th>List entry</th></tr>")
            for w in worst:
                parts.append(
                    f"<tr><td class='num'>{w.get('alerts', 0)}</td>"
                    f"<td>{html.escape(str(w.get('name', ''))[:56])}</td></tr>")
            parts.append("</table>")

    # ---- benchmark ---------------------------------------------------------
    if benchmark:
        parts.append("<h2>Does this behave like a real filter?</h2>")
        parts.append(
            "<p>Sweden's financial regulator tested 19 banks against 5,000 "
            "sanctioned names in 2024. Average accuracy was "
            f"<strong>{_pct(benchmark.get('fi_accuracy_correct_spelling'))}</strong> "
            "on correctly spelled entries. It reported accuracy fell on aliases "
            "and transliterations <em>without publishing a figure</em>.</p>"
            "<p>This study measures exactly that case, and finds "
            f"<strong>{_pct(benchmark.get('recall_within_industry_alert_rate'))}</strong> "
            "at a comparable alert rate. The gap between those two numbers is the "
            "one the regulator did not publish.</p>"
        )

    # ---- reasons not to believe it -----------------------------------------
    parts.append("<h2>Reasons not to act on this</h2>")
    parts.append(
        '<div class="note">'
        "<strong>Name-only matching.</strong> Production filters also compare "
        "country, address and date of birth. Alert volumes here are an upper "
        "bound.<br><br>"
        "<strong>Corporate population.</strong> The headline is measured on "
        "entity names. Individuals show a lower floor "
        f"({_pct(individuals.get('unreachable_rate', 0))} against "
        f"{_pct(individuals.get('entity_unreachable_rate', 0))}), so the ceiling "
        "is real on both but shallower where most screening happens.<br><br>"
        "<strong>Two inputs remain estimates</strong> — the share of misses that "
        "become enforcement actions, and the remediation multiple. Both are "
        "unknowable from public data and are swept across orders of magnitude "
        "rather than defended.<br><br>"
        "<strong>The specific threshold should not leave this document.</strong> "
        "It illustrates how the decision is framed. It is not a decision."
        "</div>"
    )

    parts.append(
        "<footer>Every figure regenerates from public data: OFAC's SDN list, "
        "OFAC's published enforcement record, and a public legal-entity "
        "register. Ground truth comes from OFAC's own alias file rather than "
        "from labelling. Generated "
        f"{datetime.now(timezone.utc).isoformat(timespec='seconds')}."
        "</footer>"
    )
    parts.append("</div></body></html>")
    return "".join(parts)


def write(evidence_dir: str | Path, out_path: str | Path) -> Path:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(evidence_dir), encoding="utf-8")
    return out
