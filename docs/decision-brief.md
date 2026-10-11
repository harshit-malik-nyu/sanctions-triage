# Where should candidate retrieval and alert review improve?

**Recommendation:** Audit prefix-blocking losses before choosing a threshold; use secondary identifiers for identity resolution.

This is an independent analytical case study. No client engagement, deployment, stakeholder acceptance or realized financial outcome is asserted.

## Decision and alternatives

Consider tune thresholds; improve retrieval; enrich identifiers. The decision owner is the operator responsible for the workflow. An analyst owns evidence quality; the workflow owner owns review capacity and the acceptable error cost. These are proposed responsibilities, not named stakeholders who approved the work.

## Evidence and correction

The blocker can miss a greater-than-90 similarity pair. Zero hit scores in the frozen blocked pipeline are not a universal ceiling. The declared CLI now exists.

Exhaustive-vs-blocked fixtures isolate retrieval defects without new sanctions data or claims of compliance certification. `analysis/output/manifest.json` identifies inputs, their hashes and observation counts. `analysis/questions.sql` exposes the aggregation and denominators; `analysis/build.py` rebuilds it locally. The source snapshot is the source of truth for descriptive claims. Earlier notebooks, figures and evidence JSON describe their original run unless explicitly regenerated.

## Economics and sensitivity

`analysis/business_case.py` executes a transparent planning model. Inputs in `analysis/assumptions.json` are illustrative: 10,000 cases per period, 22 baseline minutes, 15 assisted minutes, $60 per hour and $5,000 fixed cost. Net period value equals cases × [(baseline − assisted minutes) × hourly cost / 60 − quality-loss cost per case] − fixed cost. The committed output shows assisted time at 0.5×, 1× and 1.5× and calculates break-even volume. A nonpositive unit benefit has no finite break-even. Labor capacity released is not cash savings unless staffing or spend changes.

The zero quality-loss-cost input is an explicit scenario assumption. It must not erase the project's primary risk. Prefer an option only if it passes the safety/quality criteria and remains economical under plausible adverse assumptions. Do not monetize false positives, missed harms or causal business impact using unsupported point estimates.

## Product measurement

Primary metric: **Recovered known aliases / held-out aliases, with retrieval recall separated from scoring recall.**

Guardrails: False-alert workload on labeled negatives, review capacity and unresolved identity.

A terminal screen is a review candidate or no candidate; name similarity alone is never identity proof. Instrument each workflow with `started`, then one `completed` or `failed` event. Sessions still open remain incomplete in the denominator. `analysis/product.py` rejects duplicated events, invalid transitions, negative or nonfinite elapsed time, mixed evidence sources and unexpected fields. Only opaque session/event IDs, event type, elapsed milliseconds and evidence source are permitted. Do not log names, prompts, documents or case data.

The checked-in `events.synthetic.jsonl` is a small contract fixture: one completed, one failed and one incomplete session. Its completion rate is a QA expectation, not usage evidence. Actual adoption remains unmeasured. For an offline package, replaying known cases and validating these contracts is the achievable substitute for waiting on real users.

## Experiment and acceptance

For a future product comparison, randomly assign at the independent case or user level before exposure, keep assignment stable, and analyze intention-to-treat. Use an independent calibration split where thresholds are learned. Cluster repeated observations by household, paper, contract or user as appropriate. Fix the primary outcome and stopping point before inspection. Retain failures and attrition; do not remove hard cases after assignment.

Illustrative planning: a 50% baseline completion rate and a 5 percentage-point minimum effect require approximately 1,570 independent units per arm at two-sided 5% significance and 80% power using the conservative normal approximation. This is a design example, not an executed experiment or promised detectable effect under clustering. Multiply by the justified design effect for clustered units. A successful QA fixture does not substitute for this causal experiment.

For the delivered offline version, acceptance means all available offline regressions pass, evidence queries reconcile to input counts, deterministic rebuilds reproduce the same output hashes, and unsupported claims remain explicitly scoped. A statistical certificate additionally requires its documented iid, fixed-policy and calibration assumptions. If these fail, report inconclusive or infeasible rather than silently relaxing the threshold.

## Interview walkthrough

Explain the business decision first, then trace one result through the SQL to its source. Demonstrate the failure case that motivated the correction. Change an economic input and describe the decision boundary. Close by separating measured retrospective evidence, simulated validation and what remains unknown. This demonstrates data, business and product analysis without implying experience or outcomes the repository cannot establish.
