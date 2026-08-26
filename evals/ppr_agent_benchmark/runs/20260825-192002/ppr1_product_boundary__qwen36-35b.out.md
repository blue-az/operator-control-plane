**PPR AGENT — PRODUCT BOUNDARY BRIEFING**

---

### SURFACES

1. **Registry tools** — static catalog of 15 registered tool functions used for data queries.
2. **CLI `./ppr`** — command-line entry point; supports `query` (executes deterministic tool plans) and `gate` (inspects charter policy without querying data).
3. **Charter / PBC** — gate ruleset enforcing pattern precedence, company-code normalization, and year bounds (RUL-001/002/003). Missing charters fail closed.
4. **Analyst Desk** — published device subset; a curated layer over the full registry.

---

### DATA_BOUNDARY

PPR Agent is an **analytical historical registry only**. It queries three companies (MDT, ABT, BSX) covering 18 years (2008–2025).

- **Not clinical monitoring or device programming.**
- **PDF extraction is offline ingestion** and is not part of the live query path.
- Natural-language input follows a **deterministic plan-building/tool-dispatch** pattern; this system is **not a chatbot or free-text LLM assistant**.

---

### NON_GOALS

- Real-time clinical monitoring.
- Device programming functionality.
- Online/offline PDF ingestion within query execution.
- Conversational or generative LLM responses.

---

### NUMBERS

| Scope | Devices | Implants |
|---|---|---|
| Full registry (`devices.json`) | **3,576** device models | 92,071,191 registered US implants |
| Analyst Desk (published subset) | **1,483** devices | — |

The published subset (**1,483**) represents **41.5 %** of the full registry (**3,576**).

*Illustrative query result (MDT vs ABT ICDs, 2023):* MDT led with 918,205 implants across 60 device models; ABT had 423,440 across 32 models. HHI for 2023 ICD market: 3,912 (High concentration).

---

### RISK_NOTES

- **Charter gaps:** Missing charters fail closed; partial parses remain fail-open by policy but surface `partial_charter_parse`/`fallback` diagnostic lines.
- **Year bounds:** Years outside 2008–2025 are warned and capped, not hard-denied (e.g., `"mdt 2030"` → capped to 2025).
- **Company-code normalization** is required; raw names like "St Jude" map to `null` without RUL-002 normalization.
