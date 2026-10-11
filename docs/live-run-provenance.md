# Live run and validated snapshot

The previously configured live study ran automatically during publication on October 11, 2026. Its complete results remain preserved in commit [`d67ffe2207957f7c30ff3c1c338505e7478cbc5a`](https://github.com/harshit-malik-nyu/sanctions-triage/commit/d67ffe2207957f7c30ff3c1c338505e7478cbc5a).

The current `evidence/`, analysis outputs and decision brief intentionally use the earlier, reviewed snapshot identified in `evidence/provenance.json`. Mixing a newly downloaded population with the previously validated decision brief would make its numbers inconsistent. The live run is a separate study, not evidence that the original results generalize to another population.

Future live studies are manually triggered and uploaded as artifacts. They cannot overwrite the reviewed evidence or public brief. Offline tests and reproducible analysis continue on each push.
