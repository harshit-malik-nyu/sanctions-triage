"""Validate local event exports and summarize completion. Offline QA is not adoption."""
from pathlib import Path
import argparse, json, math
EVENTS={'started','completed','failed'}
def summarize(rows):
 sessions={};ids=set()
 for r in rows:
  if set(r)!={'event_id','session_id','event','elapsed_ms','source'}:raise ValueError('invalid event fields; never include raw user input')
  if r['event_id'] in ids:raise ValueError('duplicate event_id')
  ids.add(r['event_id'])
  if r['event'] not in EVENTS or r['source'] not in {'synthetic_qa','local_opt_in'}:raise ValueError('unknown event or source')
  if not isinstance(r['elapsed_ms'],(int,float)) or not math.isfinite(r['elapsed_ms']) or r['elapsed_ms']<0:raise ValueError('invalid elapsed time')
  s=sessions.setdefault(r['session_id'],[])
  if s and (r['elapsed_ms']<s[-1]['elapsed_ms'] or r['source']!=s[0]['source']):raise ValueError('out of order or mixed session')
  if (not s and r['event']!='started') or (s and (r['event']=='started' or s[-1]['event'] in {'completed','failed'})):raise ValueError('invalid lifecycle')
  s.append(r)
 result={}
 for source in sorted({r['source'] for r in rows}):
  selected=[s for s in sessions.values() if s[0]['source']==source]
  completed=sum(s[-1]['event']=='completed' for s in selected)
  failed=sum(s[-1]['event']=='failed' for s in selected)
  result[source]={'started':len(selected),'completed':completed,'failed':failed,'incomplete':len(selected)-completed-failed,'completion_rate':completed/len(selected) if selected else None}
 return result

def main():
 p=argparse.ArgumentParser();p.add_argument('events',type=Path);a=p.parse_args()
 print(json.dumps(summarize([json.loads(x) for x in a.events.read_text().splitlines() if x.strip()]),indent=2))
if __name__=='__main__':main()
