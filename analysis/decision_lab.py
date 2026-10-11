"""Offline decision laboratory. Planning assumptions and synthetic behavior, not ROI/adoption."""
from pathlib import Path
import csv
import hashlib
import json
import math
import random
import sqlite3

ROOT = Path(__file__).resolve().parent


def economics(spec, volume_factor=1.0, cost_factor=1.0, risk_factor=1.0):
    """Activity-based cost: explicit units, cash outlay vs capacity, independent risk gate."""
    volume = spec['volume'] * volume_factor
    rows = []
    for option in spec['options']:
        components = []
        resource_hours = 0.0
        for item in option['activities']:
            quantity = volume * item['units_per_case']
            expense = quantity * item['usd_per_unit'] * cost_factor
            components.append({'activity': item['name'], 'unit': item['unit'],
                               'quantity': quantity, 'economic_cost_usd': expense,
                               'cash_outlay_usd': expense if item['cash'] else 0.0})
            if item['unit'] == 'reviewer_hour':
                resource_hours += quantity
        expected_incidents = volume * option['incident_rate'] * risk_factor
        # Scenario loss is separate from unacceptable-harm constraints.
        risk_cost = expected_incidents * spec['loss_per_incident_usd']
        total = option['fixed_usd'] + sum(x['economic_cost_usd'] for x in components) + risk_cost
        cash = option['fixed_usd'] + sum(x['cash_outlay_usd'] for x in components)
        feasible = (option['incident_rate'] * risk_factor <= spec['max_incident_rate']
                    and resource_hours <= spec['review_capacity_hours'])
        rows.append({'option': option['name'], 'volume': volume, 'components': components,
                     'economic_cost_usd': round(total, 2), 'cash_outlay_usd': round(cash, 2),
                     'scenario_loss_usd': round(risk_cost, 2),
                     'expected_incidents': round(expected_incidents, 4),
                     'reviewer_hours': round(resource_hours, 3), 'feasible': feasible,
                     'risk_gate_pass': option['incident_rate'] * risk_factor <= spec['max_incident_rate'],
                     'capacity_gate_pass': resource_hours <= spec['review_capacity_hours']})
    feasible = [r for r in rows if r['feasible']]
    winner = min(feasible, key=lambda r: r['economic_cost_usd'])['option'] if feasible else None
    return {'volume_factor': volume_factor, 'cost_factor': cost_factor,
            'risk_factor': risk_factor, 'recommended_if_assumptions_hold': winner, 'options': rows}


def crossover(spec):
    """Solve linear total-cost crossing against baseline, then separately test feasibility."""
    base = spec['options'][0]
    def variable(o):
        return sum(a['units_per_case'] * a['usd_per_unit'] for a in o['activities']) + o['incident_rate'] * spec['loss_per_incident_usd']
    result = []
    for o in spec['options'][1:]:
        benefit = variable(base) - variable(o)
        fixed_delta = o['fixed_usd'] - base['fixed_usd']
        result.append({'option': o['name'], 'relative_to': base['name'],
                       'unit_economic_advantage_usd': round(benefit, 6),
                       'additional_fixed_usd': fixed_delta,
                       'minimum_integer_volume_to_break_even': max(0, math.ceil(fixed_delta / benefit)) if benefit > 0 else None,
                       'qualification': 'Positive unit advantage required; risk and capacity gates still apply.'})
    return result


def simulate(spec):
    """Seeded, balanced assignment within cohort/segment; user is the analysis unit."""
    rng = random.Random(spec['seed'])
    rows = []
    for cohort in range(0, 56, 7):
        for segment in spec['segments']:
            for i in range(160):
                arm = 'treatment' if i % 2 else 'control'
                p = segment['control_activation'] + (segment['treatment_delta'] if arm == 'treatment' else 0)
                started = int(rng.random() < segment['start_probability'])
                completed = int(started and rng.random() < p)
                activated = int(completed and rng.random() < segment['apply_probability'])
                incident = int(completed and rng.random() < (segment['treatment_incident'] if arm == 'treatment' else segment['control_incident']))
                returned7 = int(activated and rng.random() < segment['return7'])
                returned28 = int(activated and rng.random() < segment['return28'])
                rows.append((f'synthetic-{len(rows):05}', cohort, segment['name'], arm,
                             started, completed, activated, incident,
                             returned7 if cohort + 7 <= 56 else None,
                             returned28 if cohort + 28 <= 56 else None))
    return rows


def wilson(success, n):
    if not n:
        return None
    p, z = success / n, 1.959963984540054
    center = (p + z*z/(2*n)) / (1+z*z/n)
    half = z * math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / (1+z*z/n)
    return [max(0, center-half), min(1, center+half)]


def difference(ts, tn, cs, cn):
    """Newcombe interval from independent Wilson intervals; accounts for boundary rates."""
    if not tn or not cn:
        return None
    t, c = ts/tn, cs/cn
    tl, tu = wilson(ts, tn)
    cl, cu = wilson(cs, cn)
    delta = t-c
    return {'treatment_rate': t, 'control_rate': c, 'difference': delta,
            'ci95': [max(-1, delta-math.sqrt((t-tl)**2+(cu-c)**2)),
                     min(1, delta+math.sqrt((tu-t)**2+(c-cl)**2))]}


def experiment(rows, spec):
    groups = {a: [r for r in rows if r[3] == a] for a in ['control', 'treatment']}
    c, t = groups['control'], groups['treatment']
    primary = difference(sum(r[6] for r in t), len(t), sum(r[6] for r in c), len(c))
    guard = difference(sum(r[7] for r in t), len(t), sum(r[7] for r in c), len(c))
    primary_pass = primary['ci95'][0] > spec['minimum_activation_lift']
    guard_pass = guard['ci95'][1] < spec['maximum_incident_increase']
    n = len(rows)
    # Balanced design; continuity-corrected chi-square(1) allocation diagnostic.
    chi = max(0, abs(len(t)-n/2)-0.5)**2/(n/2)*2
    srm_p = math.erfc(math.sqrt(chi/2))
    p0 = spec['planning_baseline']
    d = spec['minimum_detectable_effect']
    p1 = p0+d
    pooled = (p0+p1)/2
    gap = d - spec['minimum_activation_lift']
    if gap <= 0:
        raise ValueError('Planning alternative must exceed the launch margin')
    per_arm = math.ceil((1.959964*math.sqrt(2*pooled*(1-pooled)) +
                         0.841621*math.sqrt(p0*(1-p0)+p1*(1-p1)))**2 / gap**2)
    incident_p = spec.get('planning_incident_rate', .01)
    guard_n = math.ceil(2*incident_p*(1-incident_p)*(1.959964+.841621)**2 /
                        spec['maximum_incident_increase']**2)
    return {'status': 'SYNTHETIC QA ONLY; never a causal claim about real users',
            'unit': spec['randomization_unit'], 'primary': primary, 'incident_itt': guard,
            'n_control': len(c), 'n_treatment': len(t), 'allocation_p': srm_p,
            'primary_gate_pass': primary_pass, 'guardrail_gate_pass': guard_pass,
            'decision': 'ELIGIBLE FOR A REAL PILOT, NOT A REAL SHIP DECISION' if primary_pass and guard_pass and srm_p >= .001 else 'HOLD',
            'planning_primary_n_per_arm': per_arm, 'planning_guardrail_n_per_arm': guard_n,
            'planning_n_per_arm': max(per_arm, guard_n),
            'planning_note': 'Approximate per-endpoint power .80 with 95% intervals; primary alternative exceeds the nonzero launch margin. Guardrail assumes .01 incidence and no true increase. Maximum is a starting budget, not guaranteed joint power; simulate joint power and rare-event behavior before a real trial. Cluster randomization needs design-effect inflation. No peeking.',
            'segment_note': 'Segment estimates are exploratory and not independent discoveries. Confirm a prespecified interaction before segment rollout.'}


def build():
    spec = json.loads((ROOT/'decision_spec.json').read_text(encoding='utf-8'))
    out = ROOT/'output/decision_lab'
    out.mkdir(parents=True, exist_ok=True)
    rows = simulate(spec['product'])
    db = sqlite3.connect(':memory:')
    db.execute('CREATE TABLE journeys(unit_id TEXT PRIMARY KEY, cohort_day INTEGER, segment TEXT, arm TEXT, started INTEGER, completed INTEGER, activated INTEGER, incident INTEGER, retained7 INTEGER, retained28 INTEGER, CHECK(activated<=completed AND completed<=started), CHECK(incident<=completed))')
    db.executemany('INSERT INTO journeys VALUES (?,?,?,?,?,?,?,?,?,?)', rows)
    for name, query in zip(['funnel', 'cohorts', 'segments'], (ROOT/'decision_lab.sql').read_text().split(';')):
        c = db.execute(query)
        with (out/f'{name}.csv').open('w', newline='', encoding='utf-8') as f:
            w = csv.writer(f, lineterminator='\n'); w.writerow([d[0] for d in c.description]); w.writerows(c.fetchall())
    with (out/'journeys.synthetic.csv').open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f, lineterminator='\n');w.writerow(['unit_id','cohort_day','segment','arm','started','completed','activated','incident','retained7','retained28']);w.writerows(rows)
    e = spec['economics']
    scenarios = [economics(e, v, c, r) for v in [.5, 1, 2] for c in [.75, 1, 1.5] for r in [1, 2, 4]]
    results = {'evidence_status': 'ILLUSTRATIVE PLANNING ASSUMPTIONS; NOT OBSERVED ROI',
               'base_case': economics(e), 'break_even': crossover(e), 'scenarios': scenarios}
    product = experiment(rows, spec['product'])
    for name, obj in [('economics.json', results), ('experiment.json', product)]:
        (out/name).write_text(json.dumps(obj, indent=2, sort_keys=True)+'\n', encoding='utf-8')
    votes = {}
    for s in scenarios:
        key = s['recommended_if_assumptions_hold'] or 'NO FEASIBLE OPTION'
        votes[key] = votes.get(key, 0)+1
    # Grid frequency is sensitivity, never probability of success.
    report = f"# {spec['title']}\n\n{spec['executive_recommendation']}\n\n"
    report += f"**Observed evidence:** {spec['observed_evidence']}\n\n"
    report += f"**Decision owner:** {spec['decision_owner']} (proposed role, not a client).\n\n"
    report += f"**Base planning case:** {results['base_case']['recommended_if_assumptions_hold'] or 'No feasible option'}. This is conditional on the assumptions, not deployment approval.\n\n"
    report += '| Alternative | Economic cost | Cash outlay | Reviewer hours | Passes risk and capacity |\n|---|---:|---:|---:|---|\n'
    for r in results['base_case']['options']:
        report += f"| {r['option']} | ${r['economic_cost_usd']:,.0f} | ${r['cash_outlay_usd']:,.0f} | {r['reviewer_hours']:,.1f} | {r['feasible']} |\n"
    report += '\nEconomic cost includes valued staff capacity and scenario incident losses. Cash outlay excludes salaried capacity and contingent losses. These are not realized savings.\n\n'
    report += '**Sensitivity across 27 equally enumerated scenarios:** '+', '.join(f'{k}: {v}' for k,v in votes.items())+'. Grid counts are not probabilities.\n\n'
    report += f"**Synthetic product experiment:** {product['decision']}. Primary effect {product['primary']['difference']:.1%}; 95% interval [{product['primary']['ci95'][0]:.1%}, {product['primary']['ci95'][1]:.1%}]. Guardrail effect {product['incident_itt']['difference']:.1%}; interval [{product['incident_itt']['ci95'][0]:.1%}, {product['incident_itt']['ci95'][1]:.1%}]. These numbers test the decision logic, not product performance.\n\n"
    report += '**Priority order:**\n\n'+ '\n'.join(f'{i+1}. {x}' for i,x in enumerate(spec['priorities']))+'\n\n'
    report += f"**What would reverse the recommendation:** {spec['reversal']}\n\n**Remaining uncertainty:** {spec['uncertainty']}\n"
    (out/'executive-summary.md').write_text(report, encoding='utf-8')
    inputs = ['decision_lab.py','decision_spec.json','decision_lab.sql']
    manifest = {'seed': spec['product']['seed'], 'synthetic_units':len(rows),
                'source_status':'All journeys synthetic; economics assumed; observed domain evidence remains in parent manifest.',
                'inputs': {n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in inputs},
                'outputs':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.iterdir()) if p.name!='manifest.json'}}
    (out/'manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True)+'\n', encoding='utf-8')
    print(json.dumps({'project':spec['project'], 'synthetic_units':len(rows), 'scenarios':len(scenarios), 'decision':product['decision']}))


if __name__ == '__main__':
    build()
