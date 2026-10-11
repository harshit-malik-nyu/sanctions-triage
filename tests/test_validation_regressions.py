import json
from triage.match import best_match,candidate_index
from triage.cli import main

def test_prefix_blocking_can_hide_a_high_similarity_match():
 names=['ABCDCORPORATION']
 assert best_match('XBCDCORPORATION',names)[1]>90
 assert best_match('XBCDCORPORATION',names,candidate_index(names))[0]==-1

def test_cli_audits_retrieval_losses(tmp_path,capsys):
 p=tmp_path/'pairs.json';p.write_text(json.dumps([{'query':'XBCDCORPORATION','reference':'ABCDCORPORATION'}]))
 assert main(['blocking-audit',str(p)])==0
 assert json.loads(capsys.readouterr().out)['blocking_losses']==1
 assert main(['score','ACME LTD','ACME'])==0
 assert json.loads(capsys.readouterr().out)['score']==100
