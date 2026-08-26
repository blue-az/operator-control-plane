### RULES
- **RUL-001 Precedence**: Pattern precedence dictates that comparative or specific-pattern queries override generic top-device plans during deterministic plan-building/tool dispatch.
- **RUL-002 Normalization**: Company codes are normalized strictly to the three primary registry entities: `ABT`, `BSX`, and `MDT`. Unresolved names drop to `null` rather than failing outright.
- **RUL-003 Year Cap**: Years outside the 2008–2025 historical window trigger a warning or hard cap. A year value alone does not result in a hard denial; it is safely constrained to the registry bounds.

### GATE_RESULTS
- **`mdt 2030`**: `allowed=true`, `company=MDT`, `year=2030`, `year_capped=2025`. Rules hit: RUL-002 and RUL-003. The agent resolves the company normally but constrains the future year downward to the 2025 ceiling.
- **`st jude 2007`**: `allowed=true`, `company=null`, `year=2007`, `year_capped=2008`. Rule hit: RUL-003. `"st jude"` does not map to the normalized registry companies (yielding `null`), and the out-of-bounds year is constrained forward to the 2008 floor. Both remain allowed under fail-open policy.

### QUERY_VS_GATE
- **`./ppr query`**: Executes deterministic tool plans and queries live data against the analytical historical registry. It does not surface a charter policy verdict because its role is retrieval/execution, not constraint evaluation.
- **`./ppr gate`**: Inspects policy only. It evaluates parsed intent strictly against Charter/PBC rules without executing data queries or returning device/implant statistics.

### FAILURE_MODES
- **Missing Charter**: Fails closed immediately if foundational parsing context is entirely absent.
- **Partial Charter Parse**: Remains fail-open by policy to prevent blocking live queries, but explicitly surfaces `partial_charter_parse` / `fallback` diagnostic lines to alert of degraded parse confidence.
