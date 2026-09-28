# The case against this analysis

The strongest argument I can make that this work should not drive a decision.
Several of these objections are supported by the study's own measurements, and
where one is decisive it says so.

---

## 1. The population is wrong for the conclusion

This screens **corporate entities against corporate entities**: real registered
companies from a legal-entity register, matched against the SDN list's entity
entries.

Most sanctions false positives in a real bank come from **individual names** —
transliterated Arabic, Persian, Russian and Chinese personal names reaching a
Latin-script list through inconsistent romanisation. `MOHAMMED` has dozens of
accepted spellings; `ACME TRADING LTD` has one.

The 15.1% unreachable figure is measured on entity aliases, which skew toward
acronyms and trading names. Individual aliases skew toward spelling variants,
which **are** reachable by fuzzy matching. The headline recommendation could
invert on a personal-name population.

**This is the most serious objection in the list**, and the study does not
answer it. Individual screening raises a privacy problem the entity population
avoids, which is why the scope was set here — but scope chosen for convenience
is still scope that limits the conclusion.

## 2. Real filters use more than names

Production screening compares **country, address, date of birth, registration
number and identifier fields** alongside the name. This study uses names alone.

That inflates the false-positive rate, possibly by a lot: `IRIS MARINE SERVICES
PRIVATE LIMITED` (India) versus `IRISL MARINE SERVICES` (Iran) is a 97.6 name
match that a country comparison would down-rank immediately.

So the alert volumes here are an upper bound on a name-only filter, not an
estimate of what a real bank runs. The recommendation to invest in identifiers
survives this — it is the same point from the other direction — but the
specific cost figures do not transfer.

## 3. The base rate makes the cost model nearly arbitrary

Expected exposure is `screenings × true_sanctioned_rate × (1 − recall) ×
cost_per_miss`. Two of those four are my estimates, and the true-sanctioned
rate is a guess at one in a million.

Move it one order of magnitude and the cost-optimal threshold moves
substantially. The study reports that as instability rather than hiding it, but
"the answer depends on a number I made up" is a real limitation however
prominently it is disclosed.

## 4. A 15% unreachable rate may be an artefact of hold-one-out

Holding an alias out removes it from the watchlist. If a party has only two
published names and they share nothing — `COIBA` and its primary — then holding
one out makes the other unreachable by construction.

A real filter has both. The party is caught, because the list contains the very
string presented.

**The honest scope of the 15.1% claim is narrower than the headline implies:**
it is the share of aliases unreachable *when that specific variant has not been
published*. That is the right question for an unknown variant, and the wrong
one for a variant already on the list. The study measures the former and the
recommendation leans on it; a reader could reasonably say the latter is what a
bank actually faces most of the time.

## 5. Name screening is the wrong control to optimise

Sanctions evasion at scale does not usually involve presenting a designated
name and hoping the filter misses. It involves front companies, nominee
ownership, layered intermediaries and trade-based value transfer — none of which
name screening touches at all.

A bank that perfected name matching would still miss the evasion that matters.
Arguing about thresholds may be arguing about the wrong control entirely, and
this study's framing takes the control's importance for granted.

## 6. "Buy identifiers" is easy to recommend and hard to do

The recommendation is directionally right and operationally glib. Identifier
capture means changing onboarding, renegotiating correspondent data standards,
and remediating existing customer records at enormous cost. The study attaches
no price to its own recommendation, which is precisely the criticism it makes
of vendor claims elsewhere.

## 7. The clean population is not a customer base

Legal-entity registrants are better-formed than a real bank's customer file:
consistent capitalisation, no free-text entry, no typos. Real customer data is
dirtier, which raises false positives further.

The direction is known; the magnitude is not measured here.

---

## What survives

- **The measured false-positive pairs are real** and the mechanism they
  illustrate is real. `IRIS` versus `IRISL` does not depend on any assumption.
- **The metric comparison is sound.** `token_set_ratio` scoring `APPLE INC`
  against `APPLE BANK FOR SAVINGS` at 100 is a bug in a widely-used default,
  and it is demonstrated rather than asserted.
- **The cost asymmetry direction is right**, even if the magnitude is
  contestable. Missed designations cost orders of magnitude more than wasted
  reviews, which is why precision-optimal thresholds are the wrong target.
- **The base rates did not previously exist** in public form, and they are
  reproducible from public data by anyone.

## What does not survive

The specific recommendation — "auto-clear below 92" — should not leave this
repository. It rests on a name-only filter, a corporate population, and an
invented base rate. It is an illustration of how the decision would be framed,
not a decision.

## The objection I cannot answer

Argument 1. If the unreachable-alias ceiling is a property of entity names
rather than of name matching, the headline recommendation is wrong for the
population a bank actually screens most.

Settling it requires running the same study on individual names, which
introduces a privacy exposure this project deliberately avoided. Until that
exists, treat the 15.1% as measured on entities and unproven elsewhere.
