# PPR Agent: Query vs Gate Semantics

---

## RULES

The gate subsystem enforces three charter rules (**PPR-RUL**) in sequence, regardless of whether a subsequent data `query` would even be valid:

| Rule | Purpose | Behavior |
|------|---------|----------|
| **RUL-001** — Pattern Precedence | Determines plan *type* precedence. Comparative queries (e.g. "compare Abbott and Medtronic ICDs") are dispatched to `compare_companies` before falling back to generic top-device plans. Only inspects the policy text; does not touch data. |
| **RUL-002** — Company Code Normalization | Maps vendor names/codes to canonical company codes: **ABT**, **BSX**, or **MDT**. If normalization fails (e.g. "st jude" is not a known canonical name), the company field resolves to `null`. |
| **RUL-003** — Year Cap | The supported registry range is **2008–2025**. Years outside this interval receive a warning and are *capped* to the nearest bound. A year violation **does not hard-deny** a gate pass — the gate still returns `allowed: true`. |

---

## GATE_RESULTS

### Example 1: `./ppr gate "mdt 2030"`

| Field | Value |
|-------|-------|
| **allowed** | `true` |
| **company** | `"MDT"` (resolved by RUL-002 normalization) |
| **year** | `2030` (raw input, outside range) |
| **year_capped** | `2025` (RUL-003 cap to upper bound) |
| **rules hit** | RUL-002, RUL-003 |

> 2030 is outside the registry span, but RUL-003 only warns and caps — it does not deny. Gate still passes.

### Example 2: `./ppr gate "st jude 2007"`

| Field | Value |
|-------|-------|
| **allowed** | `true` |
| **company** | `null` ("st jude" did not normalize to ABT/BSX/MDT) |
| **year** | `2007` (raw input, outside range) |
| **year_capped** | `2008` (RUL-003 cap to lower bound) |
| **rules hit** | RUL-003 |

> "St Jude" is not a registered canonical company and resolved to `null`. 2007 is before the registry floor — again capped, not denied. Gate still passes.

---

## QUERY_VS_GATE

These two surfaces are fundamentally different operations:

| Aspect | `./ppr query` | `./ppr gate` |
|--------|---------------|--------------|
| **Purpose** | Executes a deterministic tool plan against the live registry data. | Inspects policy (charter rules) *only* — no data queries run. |
| **Outputs** | Tool dispatch results with real counts, market shares, device models. | Policy verdict (`allowed`), parsed company/year, capping info, rules hit. |
| **Charter verdict** | **Does not surface** any charter policy result. | Always returns it. |

**Concrete example:**
- `./ppr query "compare Abbott and Medtronic ICDs 2023"` → runs `compare_companies` (RUL-001 precedence), returns registry data: MDT 918,205 implants vs ABT 423,440.
- `./ppr gate "mdt 2030"` → never touches the registry; only tells you the charter allows it (with year capped to 2025).

They are parallel and independent: **gate inspects policy; query executes data.**

---

## FAILURE_MODES

| Scenario | Behavior |
|----------|----------|
| **Missing charter** | Fails closed — gate denies because no policy exists to evaluate. |
| **Partial charter parse** | Remains fail-open by policy. Exposes `partial_charter_parse` and `fallback` lines in the response so the analyst is aware of the degraded parse. |
| **Year outside range** (most common) | Not a hard-failure. RUL-003 warns + caps; gate still returns `allowed: true`. |
| **Company failed normalization** | Resolves to `null` company — gate still passes, but any downstream data query may return 0 or broad results since no vendor filter is applied. |

---

### Summary

- **Gate = policy inspection only.** It never queries registry data. It normalizes inputs (RUL-002), caps years (RUL-003), and checks plan precedence rules (RUL-001).
- **Query = deterministic data execution.** It dispatches tools against the live implants registry with no charter verdict surfaced.
- Both `"mdt 2030"` and `"st jude 2007"` gate as `allowed: true` — neither year nor company value triggers a hard deny under current rules.
