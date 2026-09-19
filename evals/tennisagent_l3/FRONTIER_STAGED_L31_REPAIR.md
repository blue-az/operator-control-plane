# Luna staged L3.1 repair pass

A targeted repeat used the stabilized staged path, semantic negative-state
acceptance, and executor exception capture.

Outcome: 3/6 strict passes. The three passing tasks were partial join, weather
nearby-date trap, and bounded recovery. The remaining failures are not clean
model failures:

- contradiction and cross-source conflict fixtures were not actually present
  in the live substrate;
- the ambiguous-date task returned distinct dates, rather than an ambiguity,
  which is a truthful negative state but not the original fixture's positive
  condition.

Tool traces and executor errors are retained in
`FRONTIER_STAGED_L31_RESULT.json`. Do not promote this as a Luna capability
ranking. The result demonstrates the staged path is operational and that the
fixture must encode whether a contradiction/ambiguity exists before grading.
