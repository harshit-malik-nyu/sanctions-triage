# Where to set a sanctions screening threshold

**And why, on this evidence, the threshold is not the decision worth making.**

Built on OFAC's published sanctions list, OFAC's published enforcement record,
and a real registry of legal entities. No synthetic transactions, no generated
names, no invented labels. Every figure regenerates from
[`scripts/run_study.py`](scripts/run_study.py) and is committed in
[`evidence/`](evidence/).

---

## Recommendation

**Do not tune the threshold. Buy identifiers.**

Entity name screening against the full SDN list cannot be made both staffable
and adequately sensitive at any cut-off. That is not a tuning failure — it is a
property of the data, and it is measurable:

| | |
|---|---:|
| Highest recall at any threshold | **77.4%** |
| Alert rate required to reach it | **64% of everything screened** |
| Recall at a staffable alert rate | **39.9%** |
| Published aliases unreachable at *any* threshold | **15.1%** |

The last line is the binding constraint. **907 of 6,000 held-out aliases share
no character sequence with any other published name for the same party** —
`COIBA`, `AVIA IMPORT`, `CRYMSA`, `COPROVA`. No similarity metric reaches them,
because there is nothing to be similar to. A filter tuned to perfection still
misses one alias in seven.

### What that means for the threshold decision

No viable single policy exists under any defensible pair of constraints. A floor
low enough to clear 80% recall generates an alert queue no institution can
staff; a floor light enough to staff clears roughly a fifth of variants. The
study reports that rather than relaxing a constraint until an answer appears.

**If a number is required today**, the cheapest tiered policy that survives
costing is auto-clear below 92, escalate above 98: 19 analyst FTE, 0.16% alert
rate, and **20.3% recall at the floor** — a defensible operational choice and an
indefensible detection claim. It should be adopted alongside compensating
controls, not as the control.

**The investment case is elsewhere.** Secondary identifiers — registration
number, date of birth, address, the listing identifier itself — address the
15.1% that no matching improvement can touch. Spend on better fuzzy matching
buys movement along a frontier that tops out at 75.9%; identifier capture moves
the frontier.

### The ceiling holds on both populations

The obvious objection is that this measures corporate names, while most real
false positives come from transliterated personal names. That was tested rather
than caveated:

| Population | Unreachable at any threshold | Best recall |
|---|---:|---:|
| Entities | **15.1%** | 77.4% |
| Individuals | **9.7%** | 88.8% |

Personal names screen better, as predicted — they skew toward spelling variants
that fuzzy matching does reach, while entity aliases skew toward acronyms that
share nothing. But roughly **one alias in ten is still unreachable on the
population a bank screens most**, so the conclusion survives rather than
inverting.

Only the recall side was measured for individuals. Measuring their false
positives needs a corpus of innocent people's names, and publishing near-misses
between real private individuals and a sanctions list is an exposure this
project will not create.

### One threshold across both populations costs 19.1% of recall

Entities reach 60.9% recall at threshold 68; individuals need 82 for 60.6%. A
single threshold must satisfy the harder population, and the recall it gives up
on the other is measurable. That is a simplification usually made for
administrative convenience rather than for a reason.

### Does this behave like a real filter?

Sweden's financial regulator tested 19 banks against 5,000 sanctioned names in
2024. Average accuracy was **97.2% on correctly spelled entries**. It reported
accuracy fell on aliases and transliterations *without publishing a figure*.

Hold-one-out screening measures exactly that case. At an alert rate inside the
published industry band, this study finds **39.9%**.

The gap between those two numbers is the one the regulator did not publish.

### What would change this conclusion

- **A different population.** This screens corporate entities. Individual-name
  screening has different transliteration behaviour and may not share the
  ceiling.
- **Address and country matching.** Excluded here, standard in production, and
  both would raise precision at a given recall.
- **A validated true-sanctioned base rate.** At one in a million, precision is
  near zero at any usable recall. That figure is my estimate and it drives the
  cost balance more than any other input.

---

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
| **75.9%** | Current. |

The **15.1% unreachable** figure held steady through all three corrections,
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
