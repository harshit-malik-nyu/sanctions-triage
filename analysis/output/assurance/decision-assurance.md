# Decision assurance: sanctions-triage

Prioritize recall diagnostics and secondary identifiers. Neither low alert volume nor a high similarity threshold establishes identity or compliance.

**Evidence:** 909/6,000 held-out aliases scored zero in the historical blocked pipeline. A fixture demonstrates a greater-than-90 similarity match lost by prefix blocking; this is a retrieval defect, not an impossibility bound.

**Uncertainty:** Historical negatives are not identity-adjudicated ground truth; expected losses and incident rates here are scenario values, not legal or financial forecasts.

## Robustness of the assumed business case

| Alternative | Feasible grid cases / 27 | Worst regret when feasible | Maximum volume at fixed review capacity |
|---|---:|---:|---:|
| Current blocker plus alert review | 0 | No feasible case | 75000 |
| Expanded retrieval plus identifiers | 6 | $0.00 | 57142 |
| Exhaustive matching with manual review | 0 | No feasible case | 18000 |

**Robust minimax choice:** None. No option is feasible across the entire stress grid.

Finite assumed grid, not a probability distribution or protection outside the grid. Conditional regret never overrides feasibility. Null robust option means no unconditional recommendation. Cost regret is relative to the cheapest feasible option in that same scenario. Failure counts can overlap.

## Missing-outcome sensitivity

| Outcomes masked per arm | Primary effect bounds | Incident effect bounds | Every completion clears margins? |
|---|---:|---:|---|
| 0% | [1.8%, 1.8%] | [0.7%, 0.7%] | False |
| 5% | [-3.0%, 7.0%] | [-4.3%, 5.7%] | False |
| 10% | [-8.0%, 12.0%] | [-9.4%, 10.6%] | False |
| 20% | [-18.8%, 21.2%] | [-19.5%, 20.5%] | False |

These are identification bounds on deliberately masked synthetic outcomes, not confidence intervals or measured missingness. Failures and non-starters remain in the assigned denominator. Passing this sensitivity check would still require statistical and domain-quality gates.

## Domain measurement contract

**Decision:** Choose a retrieval and review workflow that avoids losing candidate matches before scoring.

**Primary outcome:** Adjudicated true-match retrieval recall at candidate generation, followed separately by review precision and workload.

**Denominator:** All independently adjudicated positive aliases for recall; all reviewed candidates for precision; historical zero scores are a different descriptive denominator.

**Independent unit:** Underlying entity; many aliases of one entity are not independent entities.

**Quality guardrail:** Missed-entity risk, reviewer capacity and no identity decision from string similarity alone.

**Minimum required data:** Entity/alias IDs, source provenance, blocker and scorer versions, complete candidate sets, adjudicated identity and review time.

**Missingness and failure handling:** Unadjudicated negatives remain unknown. A zero blocked score may mean not retrieved, so compare retrieval sets before scoring quality.

**Release rule:** Require verified retrieval quality and bounded review load before operational use; historical alias scores alone do not validate compliance performance.

**Reversal trigger:** A broader blocker recovers missed positives but exceeds review capacity, or entity-held-out validation reveals retrieval loss.

## Interview defense

**Does 909 of 6,000 establish an impossibility limit?**

No. It describes zero scores in one historical blocked pipeline. A fixture shows that prefix blocking can discard a high-similarity match.

**Why separate retrieval and scoring?**

A scorer cannot rescue a candidate it never receives. Measuring them separately identifies the operational cause of a miss.

## Implementation handoff

1. Freeze the eligible population, denominator, outcome horizon and proposed decision owner before comparison.
2. Reconcile assignment and outcome records at the independence unit; classify missingness without deleting cases.
3. Estimate the domain outcome and its uncertainty separately from activation. Apply risk and capacity vetoes before comparing costs.
4. Record approve, hold, or reverse with the evidence version and violated gate. An unmeasured required domain gate means HOLD.

The supplied cluster-budget grid is a planning sensitivity check with assumed ICC. It is not an estimate from real clusters and does not guarantee joint power. No stakeholder approval or real experiment is asserted.
