# Haiku staged two-task probe

The staged planner → local executor → compact synthesis probe was run at n=3
for valid linked evidence and invalid-date preservation.

After adding explicit planner system context, tolerant JSON extraction,
placeholder normalization, and branch-safe skipping of invalid visualization
steps, the bounded probe achieved **6/6**:

- valid linked evidence: 3/3;
- invalid-date preservation: 3/3.

The first runs remain retained as failures in `HAIKU_STAGED_ISSUES.jsonl`.
This is still a staged protocol result, not a full Haiku capability ranking.
