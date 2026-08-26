# PPR Agent — Product-Boundary Briefing

**Scope:** Product-boundary briefing only. All figures from the local ground-truth snapshot (HEAD `04ed8ed`). Standalone source-legible extract of the PPR_Agent CRM domain; not the full Phoenix system.

---

## SURFACES

Exactly **4 surfaces**:

1. **Registry tools** — the tool catalog.
2. **CLI `./ppr`** — command entrypoint (`query`, `run`, `gate`).
3. **Charter / PBC** — policy/gate inspection layer.
4. **Analyst Desk** — consumer of the **published** registry subset.

Tooling: the registry exposes a catalog of **15 statically registered tools**. Execution is **deterministic plan-building / tool dispatch**, **not a chatbot** and not a free-text LLM assistant.

---

## DATA_BOUNDARY

- **Analytical historical registry only** — coverage **2008–2025 (18 years)**, **3 companies** (MDT, ABT, BSX).
- **Natural-language queries are deterministic:** fixed plan-building over the **15** tools, not open-ended generation.
- **PDF extraction is offline ingestion** — a batch data-entry step; it is **not part of the live query path**.
- The Desk consumes a **published subset**, distinct from the **full** registry (see NUMBERS). The **full vs published subset** distinction is a boundary condition, not a defect.
- `./ppr gate` **inspects policy and does not execute data queries**; `./ppr query` **executes plans and does not surface a charter policy verdict**. The two are separated by design.

---

## NON_GOALS

- **Not clinical monitoring** and **not device programming**.
- **Not a live/real-time** feed — analytical historical data only.
- **Not a chatbot / free-text LLM assistant** — deterministic tool dispatch only.
- **Not the full Phoenix system** — a bounded CRM-domain extract.
- **Not a policy engine for execution** — gate and query have disjoint responsibilities.

---

## NUMBERS

Registry (full):
- **Full `devices.json`: 3,576 device models**; total **92,071,191 registered US implants**; 2008–2025 (18 years); 3 companies.
- **Desk **published subset: 1,483 devices** — published is **41.5%** of the full **3,576**.
- **15** statically registered tools.

Company totals (devices / implants):
- **MDT** 1,892 / 48,343,280
- **ABT** 1,271 / 29,111,911
- **BSX** 413 / 14,616,000

Device-category totals (devices / implants): Pacemaker 1,302 / 60,207,040; ICD 1,329 / 17,416,439; CRT-D 733 / 11,482,107; CRT-P 203 / 2,632,729; TPS 8 / 330,111; S-ICD 1 / 2,765.

Selected live query results (2023):
- `compare Abbott and Medtronic ICDs 2023` → `compare_companies`: **MDT** 23 families / 60 models / **918,205** implants; **ABT** 10 families / 32 models / **423,440**; insight = market leader MDT.
- `get_market_concentration --year 2023 --device-category ICD` → **HHI 3912.31 (High)**; shares MDT 52.96%, ABT 24.42%, BSX 22.61%. *(Top device: MDT Azure XT DR W1DR01 — 623,926.)*

---

## RISK_NOTES

- **Boundary drift risk:** the **published subset (1,483 = 41.5%)** and the **full registry (3,576)** must not be conflated; the Desk sees only the published slice.
- **Determinism vs. perception risk:** despite the NL front-end, this is **deterministic plan-building/tool dispatch**, **not a chatbot**; do not let NL phrasing imply generative answers.
- **Chartering gates:** **missing charter fails closed**; **partial charter parse remains fail-open by policy** but **exposes `partial_charter_parse` / `fallback` lines** — a policy-exposure surface that should be audited.
- **Year-range handling:** values **outside 2008–2025 warn or cap** (year_capped), and **a bare year alone does not hard-deny** (see `RUL-003` on `mdt 2030` → capped 2025; `st jude 2007` → capped 2008, company null).
- **Offline ingestion separation:** PDF extraction is **offline only** and **not in the live query path**; treat ingestion data quality as a separate, upstream concern.
- **No clinical claim:** explicitly **not clinical monitoring or device programming**; avoid any downstream clinical interpretation of the historical registry.

---

*Preserved exact facts: 4 surfaces, 15 tools, full vs published subset (3,576 vs 1,483 = 41.5%), not clinical monitoring, offline PDF ingestion, deterministic-not-chatbot.*
