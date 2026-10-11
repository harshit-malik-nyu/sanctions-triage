# Evidence analysis

Frozen OFAC held-out aliases evaluated through a prefix blocker. Zero score is a matcher failure, not a universal name-matching impossibility.

`python analysis/build.py` rebuilds the committed outputs without a database server, network or API key. The build validates domains and observation counts before running `questions.sql`. The manifest records SHA-256 input and query hashes. SQL uses explicit denominators and window functions where useful. Outputs are descriptive summaries, not new causal or user-adoption evidence.

Grain: `alias,true_id,hit_score,top_score`. Primary and unique keys in `build.py` identify observations; repeated references in citeaudit are retained because the grain is a reference check. Missing values fail ingestion instead of becoming zeros.

## Decision laboratory

`python analysis/decision_lab.py` builds a project-specific activity-based cost comparison, 27 sensitivity scenarios, break-even volumes, and a synthetic product-analysis fixture. `python analysis/test_decision_lab.py` checks safety/capacity vetoes, denominator integrity, retention censoring and boundary uncertainty.

Read `decision_spec.json` for the units, incident definition, randomization unit and every assumption. The original domain evidence remains in `output/manifest.json`; decision-lab outputs have a separate manifest. No generated behavioral row is a real user.

See `output/decision_lab/executive-summary.md`, `economics.json`, `funnel.csv`, `cohorts.csv`, `segments.csv` and `experiment.json`. The deliberately adverse treatment segment checks that improved completion cannot automatically justify a launch.
