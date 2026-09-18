# Practitioner review

Everything in this project is built from public data and published benchmarks.
Nothing in it has been checked by someone who runs a sanctions screening
function, and that is its largest remaining weakness — not because the
measurements are wrong, but because operational reality contains constraints
that no public source records.

This page exists to make that review cheap. It is twenty minutes of questions,
ordered so that the ones most likely to break the conclusion come first.

If you are reading this having done that work: the answers belong in this file,
attributed or anonymous as you prefer, including the ones that contradict what
is written elsewhere in the repository.

---

## The four that could break the conclusion

**1. Is name-only matching actually how any of this runs?**

The study screens on names alone. Real filters compare country, address, date
of birth and identifier fields alongside the name.

*What I need to know:* roughly what share of your alert volume survives once
secondary identifiers are applied? If it is a large reduction, the alert
volumes here are an upper bound so loose that the cost figures do not transfer —
and the recommendation to invest in identifiers is stronger than the analysis
can currently demonstrate.

**2. Does the unreachable-alias problem show up in practice?**

The central finding is that 15.1% of entity aliases and 9.7% of individual
aliases share no character sequence with any other published name for the same
party. `COIBA`. `ALEPH`. `AVIA IMPORT`.

*What I need to know:* when you catch a party presenting an unfamiliar name
variant, what actually catches it? If the answer is "the list already contained
that variant", then hold-one-out measures a case that rarely occurs and the
finding is narrower than stated.

**3. Is the true-hit base rate anywhere near 2.5 per million?**

Derived from published alert statistics rather than observed. It drives the
cost balance more than any other input.

*What I need to know:* an order of magnitude. Distinct sanctioned
counterparties per million parties screened — not alerts, counterparties.

**4. What fraction of misses ever become enforcement actions?**

This is the weakest number in the model and it is unknowable from public data
by construction: a miss nobody detected leaves no record. The study uses 2% and
sweeps it across two orders of magnitude.

*What I need to know:* is 2% laughable in either direction?

---

## Operational questions

**5.** Review time per alert. Published sources say 15–45 minutes and disagree
by a factor of three. Which end is right for a straightforward entity name
hit, and how much of the distribution is the long tail?

**6.** Is a false-hit list actually maintained, and what governs it? The study
treats whitelisting as a permanent volume reduction. If entries expire, get
re-reviewed on list updates, or require periodic re-approval, the saving is
smaller than modelled.

**7.** Are separate thresholds run for entity and individual screening? The
study finds a single threshold costs 19.1% recall. If that is already standard
practice, the finding is a confirmation rather than a recommendation — worth
knowing either way.

**8.** How is a threshold change actually approved? The study reports an
operating range and assumes someone picks inside it. If the real constraint is
that any change requires model validation, regulatory notification, or a
documented lookback, then the cost of *moving* the threshold dominates the
benefit of moving it, and the whole framing shifts.

---

## Questions about the recommendation itself

**9.** "Buy identifiers" is directionally right and operationally glib. What
does mandatory date-of-birth capture actually cost — onboarding change,
correspondent renegotiation, remediation of the existing customer file? The
study attaches no price to its own recommendation, which is precisely the
criticism it makes of vendor claims.

**10.** Is threshold tuning even the live question, or is it settled and the
real work elsewhere — entity resolution, payment message quality, list
management? If the latter, this project is well-executed work on a question
nobody is asking.

---

## What a review would change

Answers to 1–4 could invert the headline. Answers to 5–8 would move the cost
model from published benchmarks to observed practice. Answers to 9–10 would
tell me whether the recommendation is useful or merely correct.

Until then, the honest description of this work is: **a rigorous measurement on
public data, checked against published benchmarks, and unvalidated by anyone who
does the job.** The numbers are reproducible. Whether they describe the world a
practitioner works in is exactly what has not been established.
