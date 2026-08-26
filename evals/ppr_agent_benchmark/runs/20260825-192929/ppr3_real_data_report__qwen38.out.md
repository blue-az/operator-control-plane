# PPR Analyst Report — 2023 ICD & Device Landscape

**Source:** PPR Agent local ground-truth snapshot (repo `/home/blueaz/Python/ppr-agent`, HEAD `04ed8ed`)
**Classification:** Historical analytical registry data — **not clinical advice**, not device monitoring, not a basis for programming decisions.

---

## ICD_2023_COMPARISON

Query path: `./ppr query "compare Abbott and Medtronic ICDs 2023"` → deterministic tool `compare_companies` (selected by PPR-RUL-001 pattern precedence over generic top-device plans). Period: **2023 → 2023**, category **ICD**.

| Metric | MDT (Medtronic) | ABT (Abbott) |
|---|---|---|
| Device families | **23** | **10** |
| Total device models | **60** | **32** |
| US implants (2023) | **918,205** | **423,440** |

- MDT leads the 2023 ICD cohort with **918,205** implants — roughly **2.2×** the ABT volume.
- MDT's ICD breadth: **60 models across 23 families**. ABT's ICD breadth: **32 models across 10 families**.
- Deterministic insight emitted by the tool: *"market leader MDT with 918,205 implants."*

> All figures are US-registry implant counts for calendar year 2023 only.

---

## TOP_2023_DEVICES

Query path: `./ppr run get_top_devices --year 2023 --limit 5`

| Rank | Company | Category | Model / Family | 2023 Implants |
|---|---|---|---|---|
| 1 | MDT | Pacemaker | Azure XT DR — **W1DR01** | **623,926** |
| 2 | MDT | Pacemaker | Adapta DR — **ADDR01** | **454,869** |
| 3 | ABT | Pacemaker | Unknown — **PM2272 US R** | **383,089** |
| 4 | MDT | Pacemaker | Advisa DR MRI — **A2DR01** | **344,410** |
| 5 | BSX | Pacemaker | ACCOLADE / PROPONENT / ESSENTIO DR — **L101 / L111 / L201 / L211 / L301 / L311** | **278,000** |

- Top 5 are all **pacemaker** (non-ICD) devices, dominated by MDT (3 of 5).
- BSX appears once, spanning a multi-model DR family cluster.
- Combined top-5 volume: **≈ 2,084,094** implants.

---

## MARKET_CONCENTRATION

Query path: `./ppr run get_market_concentration --year 2023 --device-category ICD`

| Metric | Value |
|---|---|
| **HHI** | **3,912.31** |
| **Concentration level** | **High** |

| Company | 2023 ICD Market Share |
|---|---|
| **MDT** | **52.96 %** |
| **ABT** | **24.42 %** |
| **BSX** | **22.61 %** |

- HHI > 2,500 signals a **highly concentrated** market; 3,912.31 is well above the "high" threshold.
- MDT holds a **> 2×** share over both ABT and BSX individually.
- No single-firm monopoly (share < 70 %), but a **two-to-one oligopoly tilt** toward MDT is evident.

---

## SCOPE_LIMITS

1. **Not clinical data.** This is a historical US implant registry for analytical / market-research purposes only. It is **not clinical advice**, not a device-performance diagnostic, and not a monitoring or reprogramming tool.
2. **Deterministic, rule-gated queries.** The PPR Agent uses static plan-building and a 15-tool catalog; it is **not a free-text LLM chatbot** and does not generalize beyond the 3,576 registered device models.
3. **Temporal bounds.** Registry coverage is **2008 – 2025 (18 years)**. Out-of-range years are warned / capped (PPR-RUL-003), not silently dropped.
4. **Published subset ≠ full registry.** The Analyst Desk exposes **1,483 devices (41.5 %)** of the full 3,576-device registry. Top-device and concentration queries run against the full set; desk browsing does not.
5. **Company scope.** Registry covers **three manufacturers** (MDT, ABT, BSX). No other vendors are present.
6. **Offline ingestion only.** PDF / document extraction is an offline batch step; it is **not** part of the live query path.
7. **Charter gate ≠ execution gate.** `./ppr gate` inspects policy (company normalization, year capping) and does **not** run data queries; `./ppr query` executes deterministic tool plans and does **not** surface a charter verdict. A missing charter fails closed.

---

*Report compiled exclusively from the PPR Agent local ground-truth snapshot. No external data sources were consulted. Figures are immutable as of the cited HEAD commit.*
