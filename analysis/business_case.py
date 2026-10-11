"""Transparent scenario arithmetic; no claim of realized business impact."""
import json
from pathlib import Path
p=Path(__file__).resolve().parent
a=json.loads((p/'assumptions.json').read_text())
rows=[]
for factor in [0.5,1.0,1.5]:
 minutes=a['assisted_minutes']*factor
 unit=(a['baseline_minutes']-minutes)/60*a['hourly_cost']-a['quality_loss_cost']
 rows.append({'assisted_time_multiplier':factor,'net_value_per_case':unit,'net_period_value':unit*a['cases_per_period']-a['fixed_cost'],'break_even_cases':a['fixed_cost']/unit if unit>0 else None})
out={'status':a['evidence_status'],'assumptions':a,'scenarios':rows}
(p/'output').mkdir(exist_ok=True)
(p/'output/business_case.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))
