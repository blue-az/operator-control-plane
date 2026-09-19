# Fusion L3.1 — seeded challenge boundary

Status: design; one bounded local pilot only.

## Purpose

Break the current Fusion L3 quality ceiling with deterministic seeded conflicts,
not by adding arbitrary turns or verbosity. This is the final fusion attempt
before declaring the axis saturated.

## Challenge fixtures

1. **Injected contradiction** — source identifiers/timestamps disagree;
   preserve both and refuse silent reconciliation.
2. **Partial join** — one sensor source exists and the counterpart is absent;
   report the expected unmatched count.
3. **Weather provenance trap** — weather exists for a nearby date only;
   do not substitute it for the requested date.
4. **Ambiguous same-date sessions** — two valid sessions share a date;
   report both or request clarification.
5. **Cross-source metric conflict** — sources disagree on a metric;
   preserve source labels and values, do not average silently.
6. **Bounded recovery** — missing primary query permits a labeled recent-session
   recovery check, but not silent substitution.

Each fixture must contain frozen ground truth, allowed tool paths, invalid
outcomes, and a deterministic grader before model execution.

## Pilot and stop rule

- qwen3.6:35b, qwen3.8:27b, gemma4:26b;
- pinned CUDA-only single RTX 3090;
- six tasks × n=3 = 54 cells;
- native Ollama tools;
- full compact traces and iteration ledger.

If all three models remain 100% on the six seeded challenges, Fusion is marked
saturated and no further Fusion difficulty inflation is permitted. If the pilot
separates models, inspect traces and expand only the separating task family.
