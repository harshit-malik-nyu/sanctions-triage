"""Decision stress tests. Assumed economics and synthetic journeys only."""
from pathlib import Path
import hashlib
import json
import math
from decision_lab import economics, simulate

ROOT = Path(__file__).resolve().parent


def robustness(spec):
    scenarios = [economics(spec, v, c, r) for v in (.5, 1, 2)
                 for c in (.75, 1, 1.5) for r in (1, 2, 4)]
    rows = []
    for option in spec['options']:
        regrets = []
        risk_fail = capacity_fail = 0
        for scenario in scenarios:
            candidate = next(r for r in scenario['options'] if r['option'] == option['name'])
            feasible = [r for r in scenario['options'] if r['feasible']]
            risk_fail += not candidate['risk_gate_pass']
            capacity_fail += not candidate['capacity_gate_pass']
            if candidate['feasible']:
                regrets.append(candidate['economic_cost_usd'] - min(r['economic_cost_usd'] for r in feasible))
        hours = sum(a['units_per_case'] for a in option['activities'] if a['unit'] == 'reviewer_hour')
        rows.append({'option': option['name'], 'feasible_scenarios': len(regrets),
                     'total_scenarios': len(scenarios), 'risk_failures': risk_fail,
                     'capacity_failures': capacity_fail,
                     'worst_regret_when_feasible_usd': round(max(regrets), 2) if regrets else None,
                     'robust_across_grid': len(regrets) == len(scenarios),
                     'max_volume_at_fixed_capacity': math.floor(spec['review_capacity_hours']/hours) if hours else None,
                     'max_risk_multiplier': spec['max_incident_rate']/option['incident_rate'] if option['incident_rate'] else None})
    robust = [r for r in rows if r['robust_across_grid']]
    best = min(robust, key=lambda r: r['worst_regret_when_feasible_usd']) if robust else None
    return {'options': rows, 'robust_minimax_option': best['option'] if best else None,
            'no_feasible_option_scenarios': sum(s['recommended_if_assumptions_hold'] is None for s in scenarios),
            'interpretation': 'Finite assumed grid, not a probability distribution or protection outside the grid. Conditional regret never overrides feasibility. Null robust option means no unconditional recommendation.',
            'boundary_note': 'Capacity boundary holds activity rates fixed. Null capacity limit means no modeled reviewer hours; null risk multiplier means zero assumed incidents, not proof of safety.'}


def outcome_bounds(successes, observed, assigned):
    if not 0 <= successes <= observed <= assigned or assigned <= 0:
        raise ValueError('Require 0 <= successes <= observed <= assigned and assigned > 0')
    return [successes/assigned, (successes+assigned-observed)/assigned]


def missingness(rows, fraction, primary_margin, guard_margin):
    """Mask outcomes by ID hash; bound all possibilities for the hidden outcomes."""
    if not 0 <= fraction <= 1:
        raise ValueError('Missing fraction must be in [0, 1]')
    arms = {}
    for arm in ('control', 'treatment'):
        units = sorted((r for r in rows if r[3] == arm), key=lambda r: hashlib.sha256(r[0].encode()).hexdigest())
        n = len(units)
        if not n:
            raise ValueError('Both assigned arms required')
        m = math.floor(fraction*n)
        observed = units[m:]
        arms[arm] = {'assigned': n, 'missing': m,
                     'primary_bounds': outcome_bounds(sum(r[6] for r in observed), len(observed), n),
                     'incident_bounds': outcome_bounds(sum(r[7] for r in observed), len(observed), n)}
    c, t = arms['control'], arms['treatment']
    primary = [t['primary_bounds'][0]-c['primary_bounds'][1], t['primary_bounds'][1]-c['primary_bounds'][0]]
    guard = [t['incident_bounds'][0]-c['incident_bounds'][1], t['incident_bounds'][1]-c['incident_bounds'][0]]
    return {'masked_fraction': fraction, 'arms': arms, 'primary_identification_bounds': primary,
            'incident_identification_bounds': guard,
            'all_completions_clear_margins': primary[0] > primary_margin and guard[1] < guard_margin,
            'interpretation': 'Synthetic masking stress test. Identification bounds are NOT confidence intervals and do not authorize launch. Hidden outcomes may be nonrandom; no favorable imputation.'}


def cluster_budget(independent_n, mean_cluster_size, icc):
    if independent_n <= 0 or mean_cluster_size < 1 or not 0 <= icc <= 1:
        raise ValueError('Invalid cluster planning inputs')
    de = 1 + (mean_cluster_size-1)*icc
    clusters = math.ceil(independent_n*de/mean_cluster_size)
    return {'mean_cluster_size': mean_cluster_size, 'assumed_icc': icc,
            'design_effect': de, 'clusters_per_arm': clusters,
            'units_per_arm': clusters*mean_cluster_size}


def build():
    spec = json.loads((ROOT/'decision_spec.json').read_text())
    contract = json.loads((ROOT/'measurement_contract.json').read_text())
    experiment = json.loads((ROOT/'output/decision_lab/experiment.json').read_text())
    rows = simulate(spec['product'])
    result = {'evidence_status': 'ASSUMED ECONOMICS; SYNTHETIC PRODUCT STRESS TESTS',
              'robustness': robustness(spec['economics']),
              'missing_outcomes': [missingness(rows, q, spec['product']['minimum_activation_lift'], spec['product']['maximum_incident_increase']) for q in (0, .05, .1, .2)],
              'cluster_planning': [cluster_budget(experiment['planning_n_per_arm'], m, rho) for m in (5, 20) for rho in (0, .05, .2)],
              'cluster_limit': 'Equal-size cluster approximation with assumed ICC, not fitted dependence or guaranteed joint power. Small cluster counts, unequal sizes and rare outcomes need a design-specific calculation.',
              'domain_outcome_status': 'NOT MEASURED BY SYNTHETIC ACTIVATION. Use measurement_contract.json.'}
    out = ROOT/'output/assurance'; out.mkdir(exist_ok=True)
    (out/'stress-tests.json').write_text(json.dumps(result, indent=2, sort_keys=True)+'\n')
    report = f"# Decision assurance: {spec['project']}\n\n{spec['executive_recommendation']}\n\n"
    report += f"**Evidence:** {spec['observed_evidence']}\n\n**Uncertainty:** {spec['uncertainty']}\n\n"
    report += '## Robustness of the assumed business case\n\n| Alternative | Feasible grid cases / 27 | Worst regret when feasible | Maximum volume at fixed review capacity |\n|---|---:|---:|---:|\n'
    for r in result['robustness']['options']:
        regret = 'No feasible case' if r['worst_regret_when_feasible_usd'] is None else f"${r['worst_regret_when_feasible_usd']:,.2f}"
        volume = 'No modeled reviewer-hour limit' if r['max_volume_at_fixed_capacity'] is None else str(r['max_volume_at_fixed_capacity'])
        report += f"| {r['option']} | {r['feasible_scenarios']} | {regret} | {volume} |\n"
    report += f"\n**Robust minimax choice:** {result['robustness']['robust_minimax_option'] or 'None. No option is feasible across the entire stress grid.'}\n\n"
    report += result['robustness']['interpretation']+' Cost regret is relative to the cheapest feasible option in that same scenario. Failure counts can overlap.\n\n'
    report += '## Missing-outcome sensitivity\n\n| Outcomes masked per arm | Primary effect bounds | Incident effect bounds | Every completion clears margins? |\n|---|---:|---:|---|\n'
    for r in result['missing_outcomes']:
        p, g = r['primary_identification_bounds'], r['incident_identification_bounds']
        report += f"| {r['masked_fraction']:.0%} | [{p[0]:.1%}, {p[1]:.1%}] | [{g[0]:.1%}, {g[1]:.1%}] | {r['all_completions_clear_margins']} |\n"
    report += '\nThese are identification bounds on deliberately masked synthetic outcomes, not confidence intervals or measured missingness. Failures and non-starters remain in the assigned denominator. Passing this sensitivity check would still require statistical and domain-quality gates.\n\n'
    report += '## Domain measurement contract\n\n'
    for key,label in [('decision','Decision'),('primary_outcome','Primary outcome'),('denominator','Denominator'),('independence_unit','Independent unit'),('quality_guardrail','Quality guardrail'),('minimum_data','Minimum required data'),('failure_handling','Missingness and failure handling'),('release_rule','Release rule'),('reversal','Reversal trigger')]:
        report += f"**{label}:** {contract[key]}\n\n"
    report += '## Interview defense\n\n'
    for question,answer in contract['defense']:
        report += f"**{question}**\n\n{answer}\n\n"
    report += '## Implementation handoff\n\n1. Freeze the eligible population, denominator, outcome horizon and proposed decision owner before comparison.\n2. Reconcile assignment and outcome records at the independence unit; classify missingness without deleting cases.\n3. Estimate the domain outcome and its uncertainty separately from activation. Apply risk and capacity vetoes before comparing costs.\n4. Record approve, hold, or reverse with the evidence version and violated gate. An unmeasured required domain gate means HOLD.\n\nThe supplied cluster-budget grid is a planning sensitivity check with assumed ICC. It is not an estimate from real clusters and does not guarantee joint power. No stakeholder approval or real experiment is asserted.\n'
    (out/'decision-assurance.md').write_text(report)
    paths = [ROOT/'assurance.py', ROOT/'measurement_contract.json', ROOT/'decision_spec.json', ROOT/'decision_lab.py', ROOT/'output/decision_lab/experiment.json']
    manifest = {'inputs':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}, 'outputs':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.iterdir()) if p.name!='manifest.json'}}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
    print(spec['project'], 'assurance built')


if __name__ == '__main__':
    build()
