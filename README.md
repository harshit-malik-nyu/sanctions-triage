# Where to set a sanctions screening threshold

> **Validation update (2026-10-10):** The blocker can miss a greater-than-90 similarity pair. Zero hit scores in the frozen blocked pipeline are not a universal ceiling. The declared CLI now exists. See the [current decision brief](docs/decision-brief.md) and [reproducible analysis](analysis/README.md). Historical evidence and figures retain their original run context; this update supersedes conflicting claims below.


**And why, on this evidence, the threshold is not the decision worth making.**

📄 **[Read the decision brief](https://harshit-malik-nyu.github.io/sanctions-triage/)**
— one page, regenerated from live data on every run.

Built on OFAC's published sanctions list, OFAC's published enforcement record,
and a real registry of legal entities. No synthetic transactions, no generated
names, no invented labels. Every figure regenerates from
[`scripts/run_study.py`](scripts/run_study.py) and is committed in
[`evidence/`](evidence/).

---

## Recommendation

**Audit candidate retrieval before selecting a threshold or buying a matching upgrade.** The historical prefix-blocked matcher recovered at most **77.4%** of held-out entity aliases across the tested thresholds. At threshold 92 its recall was **20.3%**. These figures describe this implementation and sample.

**909 of 6,000 aliases (15.2%) received zero hit scores in the evaluated pipeline.** This does not prove that no similarity method could retrieve them. A four-character prefix blocker can discard a pair whose exhaustive similarity exceeds 90. The new `triage blocking-audit` command and regression fixture demonstrate that failure directly.

The historical individual-alias comparison reported **9.7%** zero-score cases, and the population-tuning analysis reported a **19.1%** recall loss from a single threshold. Those are retained as historical matcher measurements, not intrinsic ceilings. Exact-name overlap removal from the registry does not establish that every remaining entity is a labeled negative; alert rates should therefore not be treated as validated production false-positive rates.

Compare threshold tuning, improved candidate retrieval and secondary identifiers. Secondary identifiers can assist identity resolution, but the current evidence does not establish the return on any purchased solution. Keep review cost and capacity as explicit scenarios. No threshold here is recommended for automatic compliance clearance.

The offline decision brief and SQL outputs show what can be established from the frozen evidence without new data collection.

## What a false positive actually looks like

Statistics understate this. Real registered companies matched against real
designated entities, at scores a production filter would alert on:

| Score | Real company | Designated entity |
|---:|---|---|
| **97.6** | IRIS MARINE SERVICES PRIVATE LIMITED | IRISL MARINE SERVICES |
| 96.0 | FAMAN HOLDING S.R.L. | AMAN HOLDING PRIVATE JSC |
| 94.7 | SB Energy, Inc. | SBL ENERGY PRIVATE LIMITED |
| 94.1 | ML Invest GmbH | M INVEST, OOO |
| 94.1 | MF INVEST | M INVEST, OOO |

`IRISL` is the Islamic Republic of Iran Shipping Lines. `IRIS Marine Services`
is an unrelated Indian company. One character separates them, and three
different `M INVEST` variants each generate their own alert.

An analyst clears these by hand, at roughly twenty minutes each, forever.

---

## How the measurement works

### Ground truth without invented data

OFAC publishes `alt.csv`: real aliases for sanctioned parties — transliteration
variants, abbreviations, former names — each linked by entity number to its SDN
entry.

**Recall** holds one alias out, screens it against a watchlist containing every
other published name, and asks whether the true organisation appears anywhere in
the alert list. That is the real question: when a party presents a variant the
list has not seen, does the filter still reach it?

**False positives** come from 8,000 real registered legal entities. Any alert is
a false positive, because they are not sanctioned — verified rather than
assumed. Thirty-three exact matches against SDN entries were found and removed;
counting genuine sanctioned parties as false positives would have flattered the
headline.

### Three corrections that moved the headline

Each was found by reading individual rows, not the rate. None of the
intermediate numbers looked suspicious.

| Reported recall | What was wrong |
|---:|---|
| 37.9% | Watchlist held primary names only. No bank runs that — a real filter loads every published name, so acronym aliases were unmatchable by construction. |
| 52.3% | Strict entity-number equality. OFAC designates the same organisation repeatedly; `POPULAR REVOLUTIONARY STRUGGLE` matched `REVOLUTIONARY POPULAR STRUGGLE` at 100 and was scored a miss. |
| 57.3% | Top-1 scoring. A filter returns every hit above threshold and an analyst works the list; a correct answer at rank 2 was counted as a failure. |
| **77.4%** | Current. |

The **15.2% unreachable** figure held steady through all three corrections,
which is why it carries the recommendation rather than the recall number does.

### The metric was chosen by measurement

`token_set_ratio` — the obvious first choice — returns 100 whenever one token
set is a subset of another. `APPLE INC` scored a perfect match against `APPLE
BANK FOR SAVINGS`. Only `token_sort_ratio` separated real aliases from real
distinct companies at all:

| metric | min(alias) | max(non-match) | separation |
|---|---:|---:|---:|
| token_sort | 72.2 | 57.1 | **+15.1** |
| WRatio | 82.2 | 90.0 | −7.8 |
| token_set | 72.2 | 100.0 | −27.8 |

A negative separation means non-matches outscore genuine aliases, so any
threshold on that metric is arbitrary.

---

## The cost model

Both sides grounded in published figures, every parameter tagged `PUBLISHED`,
`ESTIMATE` or `DERIVED` ([`costs.py`](src/triage/costs.py)).

**False positive.** $20 per alert, from published benchmarks of $15–25 direct
review cost at 20–45 minutes. Deriving it independently from time and rate
assumptions gives $20.17 — agreement within a dollar, stated as a coincidence
rather than offered as corroboration.

**False negative.** Anchored to OFAC's own enforcement record: 180 published
civil penalties, 2014–2025.

| | |
|---|---:|
| Median penalty | $528,032 |
| Mean penalty | $29,164,727 |
| 90th percentile | $12,027,066 |
| Largest | $968,618,825 |

The mean exceeds the median fifty-fold because a few institutional settlements
dominate. The study anchors on the 90th percentile and reports all three,
because that choice is a judgment and burying it inside one number would
misrepresent how much rests on it.

**The resulting asymmetry: roughly 30,000 wasted reviews are worth one missed
designation.** That ratio is the decision, and it rests on an estimate — the
share of misses that ever become enforcement actions — unknowable from public
data by construction. It is swept across two orders of magnitude rather than
defended.

---

## Why the output is a range

Four of five assumptions moved the cost-optimal threshold across their plausible
ranges. A single recommended number would have misrepresented that.

The study reports the band where a policy satisfies both a staffing ceiling and
a recall floor, naming the binding constraint at each end. On current evidence
**that band is empty** — which is the finding, not a failure to produce one.

## Tiered, not single-threshold

Banks do not operate one cut-off. Policy has bands: auto-clear below a floor,
first-line review between, escalation above. The structure matters because **the
floor governs cost and the escalation point governs risk** — a single number
forces one decision to serve both purposes, which is why it is always wrong in
one direction.

Everything below the floor is discarded with no human in the loop, so recall at
the floor is the entire detection guarantee. That is the number a regulator asks
about first, and the study reports it as expected designated parties per year
discarded unseen.

---

## Reproducing

```bash
pip install -e ".[dev]"
python scripts/run_study.py
```

Pulls live OFAC data, records SHA-256 hashes of the exact list edition, and
writes everything to `evidence/`. The SDN list changes several times a week, so
a later run produces a different hash and slightly different counts.

## What has not been validated

Everything here is built from public data and published benchmarks. **Nothing
has been checked by someone who runs a sanctions screening function**, and that
is the largest remaining weakness — not because the measurements are wrong, but
because operational reality contains constraints no public source records.

[`docs/practitioner-review.md`](docs/practitioner-review.md) sets out the ten
questions that would validate or break this, ordered so the ones most likely to
invert the conclusion come first. Four of them could.

The honest description of this work is: a rigorous measurement on public data,
checked against published benchmarks, and unvalidated by anyone who does the
job. The numbers are reproducible. Whether they describe the world a
practitioner works in is exactly what has not been established.

## The case against this analysis

[`docs/against.md`](docs/against.md) — the strongest argument I can make that
this work should not drive a decision.

## License

MIT. OFAC data is public domain.
