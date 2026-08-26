# PPR Agent — Query & Gate Semantics

## RULES

The charter defines three rules the gate consults (in order) before it ever touches a data row:

| Rule | Name | What it does |
|------|------|-------------|
| **RUL-001** | Pattern precedence | Decides *which* deterministic tool plan a natural-language query maps to. Comparative phrasings (e.g. "compare A and B") are matched **before** generic top-device plans, so the specific intent wins. |
| **RUL-002** | Company-code normalization | Collapses free-text company names ("Medtronic", "mdt", "ST JUDE") onto the canonical three-letter codes **ABT / BSX / MDT**. If no canonical alias matches, the company field stays `null` rather than guessing. |
| **RUL-003** | Year cap | The registry spans **2008 – 2025**. A year outside that window triggers a **warn-or-cap** action (the value is clamped to the nearest bound) but does **not** hard-deny the request. A bare out-of-range year alone never flips `allowed` to `false`. |

## GATE_RESULTS

Two concrete `./ppr gate` invocations from the snapshot:

### 1 — `./ppr gate "mdt 2030"`

| Field | Value |
|-------|-------|
| allowed | **true** |
| company | **MDT** _(normalized from "mdt" via RUL-002)_ |
| year (requested) | **2030** |
| year_capped | **2025** _(clamped to upper bound via RUL-003)_ |
| rule hits | **RUL-002, RUL-003** |

Interpretation: the company alias resolved cleanly (RUL-002), the future year was clamped down to 2025 rather than rejected (RUL-003), and nothing triggered a deny.

### 2 — `./ppr gate "st jude 2007"`

| Field | Value |
|-------|-------|
| allowed | **true** |
| company | **null** _(no canonical ABT/BSX/MDT alias for "st jude"; RUL-002 leaves it unset)_ |
| year (requested) | **2007** |
| year_capped | **2008** _(clamped up to lower bound via RUL-003)_ |
| rule hits | **RUL-003** |

Interpretation: "St Jude" is a historical brand name that does not map to the three current canonical codes, so company is left `null` (RUL-002 does not force a guess). The pre-2008 year is capped forward to 2008 (RUL-003). Because a year cap is a warn/cap action—not a deny—`allowed` remains **true**.

## QUERY_VS_GATE

These are two **orthogonal** sub-commands; they never overlap in responsibility:

- **`./ppr query "<natural language>"`** — Builds a deterministic tool plan (selecting one of the 15 statically registered tools via RUL-001 precedence), dispatches it, and **executes the data query** against the registry (3,576 devices / 92 M implants, 2008-2025, 3 companies). It **does not surface a charter policy verdict**; the user sees results and insights only.

- **`./ppr gate "<text>"`** — Inspects the input **against the charter rules** (RUL-001 / RUL-002 / RUL-003) and returns an allow/deny + normalized fields (company, year, year_capped, rule hits). It **does not execute any data query**; no device rows, implant counts, or market-share numbers are produced.

In short: **query executes data; gate only inspects policy.**

## FAILURE_MODES

| Scenario | Behaviour |
|----------|-----------|
| **Missing charter file** | The gate **fails closed** — no verdict is returned and the operator is blocked. This is a hard stop. |
| **Partial charter parse** (some rules readable, others corrupted) | Remains **fail-open** by policy, but the output exposes diagnostic `partial_charter_parse` / `fallback` lines so the operator can see which rules were degraded and that default assumptions were applied. |
| **Out-of-range year (RUL-003)** | Not a failure per se: the year is **capped** to the nearest bound (2008 or 2025) and a warn is emitted; `allowed` stays `true`. A year alone never hard-denies. |
| **Unrecognized company name** | `company` is set to `null`; the request is **not** denied (see "st jude" example). Downstream query tools simply cannot scope to that entity and will surface all-company data if invoked separately. |
