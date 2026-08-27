# PPR Agent — Product-Boundary Briefing

> Source: local ground-truth snapshot at repo `/home/blueaz/Python/ppr-agent`,
> HEAD `04ed8ed`. Facts below are verbatim from that snapshot; no external sources used.

---

## SURFACES

PPR Agent exposes **4 surfaces**:

| # | Surface | Role |
|---|---------|------|
| 1 | Registry tools | 15 statically registered tools callable via `./ppr run <tool>` |
| 2 | CLI `./ppr` | Unified entry point: `query`, `run`, `gate` sub-commands |
| 3 | Charter / PBC | Policy gates (PPR-RUL-001 … 003); `./ppr gate` inspects policy without executing data queries |
| 4 | Analyst Desk | Published analytical read-out layer (1,483-device subset) |

The tool catalog contains **15 statically registered tools**. Natural-language input to `./ppr query` is **deterministic plan-building and tool dispatch, not a free-text LLM chatbot**.

---

## DATA_BOUNDARY

- **Scope:** Analytical historical registry of US cardiac-implant registrations, 2008–2025 (18 years), 3 manufacturers (MDT, ABT, BSX).
- **Full registry:** **3,576** device models, 92,071,191 registered US implants.
- **Published (Desk) subset:** **1,483** devices — **41.5%** of the full 3,576.
- **PDF extraction is offline ingestion** (batch loading of source documents); it is **not** part of the live query path.
- Missing charter → **fail-closed**. Partial charter parse → fail-open by policy but surfaces `partial_charter_parse` / `fallback` diagnostic lines.
- Years outside 2008–2025 trigger a **warn or cap** (e.g., `./ppr gate "mdt 2030"` → `year_capped 2025`); a bare year does **not** hard-deny.

---

## NON_GOALS

| Boundary | Stated exclusion |
|----------|-----------------|
| Clinical use | **Not clinical monitoring** and **not device programming** |
| Generative chat | **Deterministic plan-building, not a chatbot / free-text LLM assistant** |
| Live document parsing | **Offline PDF ingestion** only; no live query-path document processing |
| Full-system parity | Standalone source-legible extract of the PPR_Agent CRM domain; **not the full Phoenix system** |
| Open-ended NL | `./ppr query` executes a **deterministic tool plan**; it does not surface a charter policy verdict (that is `./ppr gate`'s job) |

---

## NUMBERS

| Metric | Value |
|--------|-------|
| Device models (full) | **3,576** |
| Device models (Desk published) | **1,483** (41.5 % of full) |
| Registered US implants (full) | 92,071,191 |
| Years covered | 2008–2025 (18 years) |
| Manufacturers | 3 (MDT / ABT / BSX) |
| Statically registered tools | **15** |
| MDT implants | 48,343,280 (1,892 devices) |
| ABT implants | 29,111,911 (1,271 devices) |
| BSX implants | 14,616,000 (413 devices) |
| ICD market HHI (2023) | 3,912.31 (High) |
| ICD share 2023 | MDT 52.96 % / ABT 24.42 % / BSX 22.61 % |

---

## RISK_NOTES

1. **Coverage gap:** The Desk published subset (1,483 / 3,576 = 41.5 %) means analysts see fewer than half of the registered device models; any Desk-only analysis under-represents the full 92-million-implant registry.
2. **Fail-open on partial charter:** A partial charter parse is fail-open by policy. Downstream consumers must treat `partial_charter_parse` / `fallback` lines as non-authoritative.
3. **Year cap, not deny:** Out-of-range years (e.g., 2030 → capped to 2025; 2007 → capped to 2008) return `allowed: true` with a cap, not a hard deny. Systems that assume hard denial on out-of-range years will misinterpret results.
4. **Determinism boundary:** `./ppr query` does **not** surface a charter policy verdict; `./ppr gate` does **not** execute data queries. Conflating the two sub-commands risks either un-gated queries or missing policy signals.
5. **Not a safety/clinical tool:** The system is explicitly an analytical historical registry. Any deployment framing that implies clinical monitoring, device programming, or patient-level decision support exceeds the stated boundary.
6. **Offline ingestion coupling:** PDF extraction is a batch/offline step. Live query correctness depends on successful prior ingestion; a stale or incomplete offline load will silently reflect in registry totals without a live-path alert.
7. **Extract, not full system:** The repo is a standalone extract of the PPR_Agent CRM domain. Features, invariants, or integrations present in the full Phoenix system are out of scope and should not be assumed here.
