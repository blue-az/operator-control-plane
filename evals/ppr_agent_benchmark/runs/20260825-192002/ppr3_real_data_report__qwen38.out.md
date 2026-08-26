# PPR Analyst Report — Historical ICD/Device Registry Facts (2023)

Source: local PPR Agent ground-truth snapshot (read-only registry extract, `04ed8ed`). All figures are historical analytical registry data only; this is **not clinical advice** and does not support device selection, monitoring, or programming decisions.

## ICD_2023_COMPARISON

Determinate plan: `compare_companies` (per PPR-RUL-001, comparative queries bind before generic top-device plans), period 2023-2023, category ICD.

| Company | Device Families | Device Models | 2023 ICD Implants |
|---------|-----------------|---------------|-------------------|
| **MDT (Medtronic)** | 23 | 60 | **918,205** |
| **ABT (Abbott)** | 10 | 32 | **423,440** |

- Combined 2023 ICD implants (these two companies): 1,341,645 across 33 families / 92 models.
- Registry insight recorded: **MDT is the period market leader with 918,205 ICD implants** — roughly 2.17× ABT's volume.
- MDT also leads on catalog depth: ~2.3× the device families (~1.88× the models) versus ABT.

## TOP_2023_DEVICES

`get_top_devices --year 2023 --limit 5` — all five are pacemakers:

| Rank | Company | Device | Implants (2023) |
|------|---------|--------|-----------------|
| 1 | MDT | Pacemaker Azure XT DR (W1DR01) | 623,926 |
| 2 | MDT | Pacemaker Adapta DR (ADDR01) | 454,869 |
| 3 | ABT | Pacemaker Unknown PM2272 US R | 383,089 |
| 4 | MDT | Pacemaker Advisa DR MRI (A2DR01) | 344,410 |
| 5 | BSX | Pacemaker ACCOLADE/PROPONENT/ESSENTIO DR (L101/L111/L201/L211/L301/L311) | 278,000 |

- MDT holds 3 of the top 5 slots; the #1 device alone (Azure XT DR) exceeds ABT's entire 2023 ICD implant count.
- Note the rank-3 entry carries an "Unknown" model designation — a data-quality artifact in the registry label, not a separate product line.

## MARKET_CONCENTRATION

`get_market_concentration --year 2023 --device-category ICD`:

- **HHI: 3,912.31 → concentration level: High** (well above the 2,500 "high concentration" threshold under standard HHI interpretation).
- 2023 ICD market shares:
  - **MDT: 52.96%**
  - **ABT: 24.42%**
  - **BSX: 22.61%**
- Shares sum to 100.00%, consistent with the 3-company registry scope. This is a 3-player market, no other competitors present in the extract.

## SCOPE_LIMITS

- **Historical analytical registry data only.** The system is an offline, source-legible extract of a CRM domain — not clinical monitoring, not device programming, not patient-level data. **This report is not clinical advice.**
- **Company scope:** only 3 manufacturers (MDT, ABT, BSX). Market shares are within this closed registry, not the open US market.
- **Time scope:** 2008–2025 (18 years). Year 2030-style requests are capped by PPR-RUL-003, not honored; 2007 requests are capped to 2008.
- **Coverage:** full registry = 3,576 device models / 92,071,191 registered US implants; the published Desk subset is only 1,483 devices (41.5% of full). Company totals in the extract: MDT 1,892 devices / 48,343,280 implants; ABT 1,271 / 29,111,911; BSX 413 / 14,616,000.
- **Query determinism:** natural-language queries map to a fixed 15-tool static catalog via deterministic plan-building — results reflect the snapshot at HEAD `04ed8ed`, not a live data feed. Charter-gated policy (`./ppr gate`) and data execution (`./ppr query`) are separate paths; missing charter fails closed, but partial charter parse remains fail-open by policy.
- **Label fidelity:** device names are as stored in the registry (e.g., "Unknown PM2272 US R", BSX combined L-series designation); they may not map 1:1 to commercial SKU naming.
