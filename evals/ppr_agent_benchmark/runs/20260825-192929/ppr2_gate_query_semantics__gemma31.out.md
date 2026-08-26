### RULES
*   **RUL-001 (Precedence):** Establishes pattern precedence, ensuring comparative queries are prioritized over generic top-device plans.
*   **RUL-002 (Normalization):** Handles company code normalization to the standard identifiers: ABT, BSX, and MDT.
*   **RUL-003 (Year Cap):** Years falling outside the 2008–2025 window are warned or capped; a year alone does not trigger a hard-deny.

### GATE_RESULTS
*   **`./ppr gate "mdt 2030"`**: 
    *   **Verdict:** `allowed: true`
    *   **Details:** Company: MDT, Year: 2030, `year_capped: 2025`.
    *   **Rules Hit:** RUL-002 and RUL-003.
*   **`./ppr gate "st jude 2007"`**: 
    *   **Verdict:** `allowed: true`
    *   **Details:** Company: null, Year: 2007, `year_capped: 2008`.
    *   **Rule Hit:** RUL-003.

### QUERY_VS_GATE
*   **`./ppr query`**: Executes deterministic tool plans to retrieve and return actual data; it does not surface a charter policy verdict.
*   **`./ppr gate`**: Inspects the request against the charter policy to determine eligibility; it does not execute data queries.

### FAILURE_MODES
*   **Missing Charter:** The system fails closed.
*   **Partial Charter Parse:** Remains fail-open by policy, though it exposes `partial_charter_parse` and `fallback` lines.
