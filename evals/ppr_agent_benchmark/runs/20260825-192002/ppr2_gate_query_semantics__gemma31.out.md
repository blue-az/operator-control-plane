### RULES
The PPR Agent operates under a set of charter rules that govern plan building and input normalization:
*   **RUL-001 (Precedence):** Establishes pattern precedence, ensuring that comparative queries are prioritized over generic top-device plans.
*   **RUL-002 (Normalization):** Mandates the normalization of company codes to a standard set: ABT, BSX, and MDT.
*   **RUL-003 (Year Cap):** Years falling outside the supported 2008-2025 range are capped or trigger a warning; however, a year value alone does not result in a hard denial.

### GATE_RESULTS
The `./ppr gate` command evaluates inputs against the charter without executing data tools:
*   **Input `"mdt 2030"`**: 
    *   **Verdict:** Allowed (true)
    *   **Normalization:** Company normalized to MDT (RUL-002)
    *   **Year Handling:** Year 2030 is capped to 2025 (RUL-003)
*   **Input `"st jude 2007"`**: 
    *   **Verdict:** Allowed (true)
    *   **Normalization:** Company is null (not matched to ABT/BSX/MDT)
    *   **Year Handling:** Year 2007 is capped to 2008 (RUL-003)

### QUERY_VS_GATE
There is a strict functional separation between the two primary CLI interfaces:
*   **`./ppr query`**: Executes deterministic tool plans to retrieve and process actual registry data. It does not surface a charter policy verdict.
*   **`./ppr gate`**: Inspects policy and charter compliance for a given input. It does not execute data queries or access the registry.

### FAILURE_MODES
*   **Missing Charter:** If the charter is missing entirely, the system fails closed.
*   **Partial Charter Parse:** A partial parse remains fail-open by policy but will expose `partial_charter_parse` and `fallback` lines in the output.
