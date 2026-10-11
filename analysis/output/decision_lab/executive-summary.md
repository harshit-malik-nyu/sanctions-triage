# Repair candidate retrieval before buying a lower alert threshold

Prioritize recall diagnostics and secondary identifiers. Neither low alert volume nor a high similarity threshold establishes identity or compliance.

**Observed evidence:** 909/6,000 held-out aliases scored zero in the historical blocked pipeline. A fixture demonstrates a greater-than-90 similarity match lost by prefix blocking; this is a retrieval defect, not an impossibility bound.

**Decision owner:** Screening operations lead (proposed role, not a client).

**Base planning case:** Expanded retrieval plus identifiers. This is conditional on the assumptions, not deployment approval.

| Alternative | Economic cost | Cash outlay | Reviewer hours | Passes risk and capacity |
|---|---:|---:|---:|---|
| Current blocker plus alert review | $218,000 | $0 | 800.0 | False |
| Expanded retrieval plus identifiers | $152,250 | $28,000 | 1,050.0 | True |
| Exhaustive matching with manual review | $317,333 | $9,000 | 3,333.3 | False |

Economic cost includes valued staff capacity and scenario incident losses. Cash outlay excludes salaried capacity and contingent losses. These are not realized savings.

**Sensitivity across 27 equally enumerated scenarios:** Expanded retrieval plus identifiers: 6, NO FEASIBLE OPTION: 21. Grid counts are not probabilities.

**Synthetic product experiment:** HOLD. Primary effect 1.8%; 95% interval [-2.1%, 5.6%]. Guardrail effect 0.7%; interval [-0.0%, 1.5%]. These numbers test the decision logic, not product performance.

**Priority order:**

1. Separate retrieval recall from conditional scoring recall at entity level.
2. Compare additional alert workload with staffed review capacity before expanding retrieval.
3. Prespecify identity-labeled negative evaluation and escalation rules; keep unresolved cases unresolved.

**What would reverse the recommendation:** If expanded retrieval exceeds review capacity or fails the missed-identity gate, increase capacity or hold deployment instead of hiding risk by raising the threshold.

**Remaining uncertainty:** Historical negatives are not identity-adjudicated ground truth; expected losses and incident rates here are scenario values, not legal or financial forecasts.
