from pathlib import Path
import importlib.util,json,pytest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('product_contract',ROOT/'analysis/product.py')
product=importlib.util.module_from_spec(spec);spec.loader.exec_module(product)

def test_events_keep_failed_and_incomplete_in_denominator():
 rows=[json.loads(x) for x in (ROOT/'analysis/events.synthetic.jsonl').read_text().splitlines()]
 out=product.summarize(rows)['synthetic_qa']
 assert out['started']==3 and out['completed']==1 and out['failed']==1 and out['incomplete']==1
 assert out['completion_rate']==pytest.approx(1/3)
 for malformed in [rows+[rows[0]],rows[1:], [{**rows[0],'raw_name':'sensitive'}], [{**rows[0],'elapsed_ms':-1}]]:
  with pytest.raises(ValueError):product.summarize(malformed)
