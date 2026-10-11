import unittest
from assurance import outcome_bounds, missingness, robustness, cluster_budget


class AssuranceTests(unittest.TestCase):
    def test_unknown_outcomes_never_disappear(self):
        self.assertEqual(outcome_bounds(2, 4, 10), [.2, .8])
        self.assertEqual(outcome_bounds(0, 0, 10), [0, 1])
        with self.assertRaises(ValueError):
            outcome_bounds(5, 4, 10)

    def test_missing_outcomes_can_reverse_apparent_win(self):
        rows = [(f'{a}{i}',0,'s',a,1,1,int(a=='treatment'),0,0,0) for a in ('control','treatment') for i in range(10)]
        self.assertTrue(missingness(rows,0,.02,.005)['all_completions_clear_margins'])
        self.assertFalse(missingness(rows,1,.02,.005)['all_completions_clear_margins'])
        self.assertEqual(missingness(rows,1,.02,.005)['primary_identification_bounds'],[-1,1])

    def test_cheapest_unsafe_option_cannot_be_robust(self):
        s={'volume':10,'review_capacity_hours':100,'loss_per_incident_usd':0,'max_incident_rate':.1,
           'options':[{'name':'safe','fixed_usd':10,'incident_rate':.01,'activities':[]},
                      {'name':'unsafe','fixed_usd':0,'incident_rate':.2,'activities':[]}]}
        self.assertEqual(robustness(s)['robust_minimax_option'],'safe')
        s['options'][0]['incident_rate']=.04
        self.assertIsNone(robustness(s)['robust_minimax_option'])

    def test_cluster_budget_rounds_up_and_inflates(self):
        a=cluster_budget(101,20,0); b=cluster_budget(101,20,.2)
        self.assertEqual(a['units_per_arm'],120)
        self.assertGreater(b['units_per_arm'],a['units_per_arm'])
        self.assertGreaterEqual(b['units_per_arm'],101*b['design_effect'])
        with self.assertRaises(ValueError):
            cluster_budget(101,20,-.1)


if __name__ == '__main__':
    unittest.main()
