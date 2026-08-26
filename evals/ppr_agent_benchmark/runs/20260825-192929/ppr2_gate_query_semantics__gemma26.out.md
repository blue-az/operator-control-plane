### RULES
* **PPR-RUL-001 (Pattern Precedence):** The agent prioritizes specific comparative query patterns over generic top-device plans.
* **PPR-RUL-002 (Normalization):** All company identifiers are normalized to the standard set: `ABT`, `BSX`, and `MDT`.
* **PPR-RUL-003 (Year Cap):** The registry covers the period 2008–2025. Dates outside this range trigger a warning or a cap; a year provided outside this range does not trigger a hard denial.

### GATE_RESULTS
* **Input: `"mdt 2030"`**
    * **Allowed:** `true`
    * **Company:** `MDT`
    * **Year:** `2030`
    * **Year_capped:** `20                25`
    * **Rules Hit:** `RUL-002` (normalization) and `RUL-003` (year cap).
* **Input: `"st jude 2007"`**
    * **Allowed:** `true`
    * **Company:** `null`
    * **Year:** `2007`
    * **Year_capped:** `2008`
    * **Rules Hit:** `RUL-003` (year cap).

### QUERY_VS_GATE
* **`./ppr query`**: Executes deterministic tool plans against the data registry to produce analytical results; it does not surface a charter policy verdict.
* **`./ppr gate`**: Inspects the input string against the established Charter/PBC policy rules; it does not execute any data queries.

### FAILURE_MODES
* **Failure-Closed:** If the Charter/PBC is entirely missing, the system fails closed.
* **Failure-Open:** If the Charter is present but cannot be fully parsed, the system remains fail-open by policy, though it exposes `partial_charter_parse` or `fallback` traces.
