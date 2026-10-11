"""Decision errors worth preventing: denominator exclusion, censoring, and unsafe winners."""
import importlib.util
from pathlib import Path
import sqlite3
import unittest

path = Path(__file__).with_name('decision_lab.py')
spec = importlib.util.spec_from_file_location('decision_lab', path)
lab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lab)


class DecisionContracts(unittest.TestCase):
    def test_primary_win_cannot_override_guardrail_failure(self):
        settings={'randomization_unit':'synthetic account','minimum_activation_lift':.02,
                  'maximum_incident_increase':.005,'planning_baseline':.4,
                  'minimum_detectable_effect':.05}
        rows=[]
        for arm in ['control','treatment']:
            for i in range(1000):
                activated=int(i < (400 if arm=='control' else 600))
                incident=int(arm=='treatment' and i<100)
                rows.append((f'{arm}-{i}',0,'x',arm,1,1,activated,incident,0,0))
        self.assertTrue(lab.experiment(rows,settings)['primary_gate_pass'])
        self.assertEqual(lab.experiment(rows,settings)['decision'],'HOLD')
        safe=[r[:7]+(0,)+r[8:] for r in rows]
        self.assertTrue(lab.experiment(safe,settings)['guardrail_gate_pass'])
        self.assertNotEqual(lab.experiment(safe,settings)['decision'],'HOLD')

    def test_unsafe_cheapest_option_is_not_recommended(self):
        s = {'volume':100, 'loss_per_incident_usd':0, 'max_incident_rate':.01, 'review_capacity_hours':100,
             'options':[{'name':'unsafe','fixed_usd':0,'incident_rate':.1,'activities':[]},
                        {'name':'safe','fixed_usd':50,'incident_rate':0,'activities':[]}]}
        self.assertEqual(lab.economics(s)['recommended_if_assumptions_hold'], 'safe')
        s['options'][1]['incident_rate'] = .2
        self.assertIsNone(lab.economics(s)['recommended_if_assumptions_hold'])

    def test_capacity_can_veto_safe_option(self):
        s={'volume':100,'loss_per_incident_usd':0,'max_incident_rate':.01,'review_capacity_hours':10,
           'options':[{'name':'review','fixed_usd':0,'incident_rate':0,'activities':[
               {'name':'review','unit':'reviewer_hour','units_per_case':.2,'usd_per_unit':50,'cash':False}]}]}
        r=lab.economics(s)['options'][0]
        self.assertFalse(r['feasible']);self.assertEqual(r['cash_outlay_usd'],0)
        self.assertEqual(r['economic_cost_usd'],1000)

    def test_zero_observed_incidents_does_not_prove_zero_risk(self):
        self.assertGreater(lab.wilson(0, 10)[1], .25)
        self.assertIsNone(lab.wilson(0, 0))
        interval=lab.difference(0,10,0,10)['ci95']
        self.assertLess(interval[0],0);self.assertGreater(interval[1],0)

    def test_sql_keeps_nonstarters_and_censors_immature_cohorts(self):
        db=sqlite3.connect(':memory:')
        db.execute('CREATE TABLE journeys(unit_id,cohort_day,segment,arm,started,completed,activated,incident,retained7,retained28)')
        db.executemany('INSERT INTO journeys VALUES (?,?,?,?,?,?,?,?,?,?)',[
            ('a',0,'x','control',1,1,1,0,1,1),
            ('b',0,'x','control',0,0,0,0,0,0),
            ('c',49,'x','control',1,1,1,0,1,None)])
        qs=path.with_name('decision_lab.sql').read_text().split(';')
        row=db.execute(qs[0]).fetchone()
        self.assertEqual(row[1],3);self.assertAlmostEqual(row[6],2/3)
        cohort=db.execute(qs[1]).fetchall()[1]
        self.assertEqual(cohort[7],0);self.assertIsNone(cohort[9]);self.assertEqual(cohort[10],1)


if __name__=='__main__':
    unittest.main()
