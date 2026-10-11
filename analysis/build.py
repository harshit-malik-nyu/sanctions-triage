"""Rebuild a typed SQLite evidence mart and query outputs using only committed inputs."""
from pathlib import Path
import csv, hashlib, json, sqlite3, sys
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'analysis/output'
sources={}
def record(path): sources[str(path.relative_to(ROOT))]=hashlib.sha256(path.read_bytes()).hexdigest()
def read_json(path):
 record(path)
 return json.loads(path.read_text())
def read_csv(path):
 record(path)
 with path.open(newline='') as f:return list(csv.DictReader(f))

rows=[(r['alias'],r['true_ent_num'],float(r['hit_score']),float(r['top_score'])) for r in read_csv(ROOT/'evidence/alias_results.csv')]

OUT.mkdir(exist_ok=True)
db=sqlite3.connect(':memory:')
db.execute('CREATE TABLE observations (alias TEXT NOT NULL,true_id TEXT NOT NULL,hit_score REAL CHECK(hit_score BETWEEN 0 AND 100),top_score REAL CHECK(top_score BETWEEN 0 AND 100))')
db.executemany('INSERT INTO observations (alias,true_id,hit_score,top_score) VALUES (?,?,?,?)',rows)
assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
assert db.execute('SELECT COUNT(*) FROM observations').fetchone()[0]==len(rows)>0
queries=(ROOT/'analysis/questions.sql').read_text().split(';')
outputs=[]
for i,query in enumerate(queries,1):
 if not query.strip():continue
 cursor=db.execute(query)
 path=OUT/f'query_{i}.csv'
 with path.open('w',newline='') as f:
  writer=csv.writer(f);writer.writerow([d[0] for d in cursor.description]);writer.writerows(cursor.fetchall())
 outputs.append(path.name)
manifest={'project':'sanctions-triage','rows':len(rows),'scope':'Frozen OFAC held-out aliases evaluated through a prefix blocker. Zero score is a matcher failure, not a universal name-matching impossibility.','input_sha256':sources,'query_sha256':hashlib.sha256((ROOT/'analysis/questions.sql').read_bytes()).hexdigest(),'outputs':{n:hashlib.sha256((OUT/n).read_bytes()).hexdigest() for n in outputs},'quality_checks':['SQL type and domain constraints','row-count reconciliation','SQLite integrity'],'external_services_required':False}
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
print(json.dumps({'project':'sanctions-triage','rows':len(rows),'outputs':outputs}))
