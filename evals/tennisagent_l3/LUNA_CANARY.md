# Luna frontier canary

One-tool canary after parser conformance validation.

- Endpoint: Luna via external JSON adapter
- Task: retrieve linked session data for 2026-01-05, then finalize
- Tool contract: passed (one valid tool call and final JSON)
- Wall-clock: 13.106 s
- Semantic final: usable but incomplete — reported 40 swing records and IDs,
  but omitted the Apple Watch session and linkage summary.

This is transport and bounded-answer evidence only, not a capability ranking.
