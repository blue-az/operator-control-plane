### RULES
The PPR Agent operates under a defined set of charter rules that govern input processing:
*   **RUL-001 (Precedence):** Defines pattern precedence, ensuring that comparative queries are prioritized over generic top-device plans.
*   **RUL-002 (Normalization):** Enforces company code normalization to the standardized set: **ABT**, **BSX**, and **MDT**.
*   **RUL-003 (Year Cap):** Handles years outside the 2008–2025 range by applying a warning or a cap; a year value alone does not trigger a hard denial.

### GATE_RESULTS
The following results demonstrate the behavior of the `./ppr gate` command:

1.  **Input:** `./ppr gate "mdt 2030"`
    *   **Allowed:** `true`
    *   **Company:** `MDT`
    *   **Year:** `2030`
    *   **Year Capped:** `2025`
    *   **Rules Triggered:** `RUL-002`, `RUL-003`

2.  **Input:** `./ppr gate "st jude 2007"`
    *   **Allowed:** `true`
    *   **Company:** `null`
    *   **Year:** `2007`
    *   **Year Capped:** `2008`
    *   **Rules Triggered:** `RUL-003`

### QUERY_VS_GATE
The two primary interfaces of the agent serve distinct functional purposes:
*   **`./ppr query`** executes deterministic tool plans against the data registry to retrieve analytical results. It does not surface charter policy verdicts.
*   **`./ppr gate`** is used solely to inspect the charter policy for compliance and does not execute data queries.

### FAILURE_MODES
*   **Missing Charter:** The system fails **closed**.
*   **Partial Charter Parse:** The system remains **fail-open** by policy, though this state exposes `partial_charter_parse` or `fallback` lines.
