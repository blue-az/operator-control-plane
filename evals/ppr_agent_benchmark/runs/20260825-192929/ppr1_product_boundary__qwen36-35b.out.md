# PPR Agent Product-Boundary Briefing

**SURFACES**
- Registry tools
- CLI `./ppr`
- Charter/PBC
- Analyst Desk
*(Explicitly 4 surfaces)*

**DATA_BOUNDARY**
Historical implant/device registry spanning 2008–2025 (18 years) across three manufacturers: MDT, ABT, and BSX. Query execution translates natural-language input into structured execution plans via a catalog of **15 tools**, routing to comparative or summary registries based on pattern precedence (PPR-RUL-001). The Analyst Desk operates using a curated **full vs published subset** of the backend registry; the remainder stays in `devices.json` but is not surfaced to desk users. Company codes normalize to ABT/BSX/MDT, and out-of-range years trigger warnings or caps (RUL-003) without hard-deny.

**NON_GOALS**
- Explicitly **not clinical monitoring** or device programming.
- Data enrichment via **offline PDF ingestion**; never part of the live query path.
- Input handling is **deterministic-not-chatbot**: the system builds fixed tool-dispatch plans rather than acting as a free-text LLM assistant or surfacing policy verdicts during standard `./ppr query` runs.

**NUMBERS**
- Backend registry: **3576** device models across 92,071,191 registered US implants.
- Analyst Desk published subset: **1483** devices.
- Published represents **41.5%** of the full registry coverage.
- Representative 2023 landscape: Top pacemaker (MDT Azure XT DR) held 623,926 implants; ICD market concentration reached HHI 3912.31 with MDT leading at 52.96% share.

**RISK_NOTES**
- Charter policy gaps are handled strictly: missing charters fail closed; partially parsed charters remain fail-open by policy but emit `partial_charter_parse`/fallback logs that require observability monitoring.
- Year inputs outside the 2008–2025 window are warned/capped rather than rejected, which may mask legacy or future-state queries if users assume hard boundaries.
- Query routing respects pattern precedence: comparative intents override generic top-N defaults, meaning desk users expecting broad rankings on company names will receive targeted comparative outputs instead.
