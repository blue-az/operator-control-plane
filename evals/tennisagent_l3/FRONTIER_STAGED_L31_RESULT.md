# Frontier staged L3.1 canary

Protocol: planner JSON → local deterministic executor → compact evidence →
synthesis. One trial per six seeded task prompts, for each model.

| Model | Result |
|---|---:|
| Claude Haiku | 6/6 |
| Luna | 2/6 |

This is a canary, not a capability ranking. Haiku completed all six staged
planner/executor/synthesis paths. Luna completed the first two, then produced
incomplete or semantically insufficient synthesis on the remaining tasks;
several traces still contain valid tool selection. Raw rows are retained in
`FRONTIER_STAGED_L31_RESULT.json`.
