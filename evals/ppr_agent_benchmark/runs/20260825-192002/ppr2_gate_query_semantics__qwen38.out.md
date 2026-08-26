## RULES

The PPR Agent is governed by a charter of deterministic rules that the gate surface inspects:

- **RUL-001 (pattern precedence):** Comparative/comparison-shaped queries take precedence over generic top-device plans. This is why `./ppr query "compare Abbott and Medtronic ICDs 2023"` dispatches to `compare_companies` rather than falling back to a generic top-devices plan.
- **RUL-002 (company code normalization):** Free-form company names are normalized to the canonical codes **ABT / BSX / MDT** (e.g., "Medtronic" → MDT, "St. Jude" / "Saint Jude" → BSX) before any downstream processing.
- **RUL-003 (year cap):** Years outside the registry's 2008–2025 window trigger a warning and a cap to the nearest in-window boundary; a year by itself never hard-denies a request.

## GATE_RESULTS

- `./ppr gate "mdt 2030"` → **allowed: true**, company **MDT**, year 2030, **year_capped 2025**, rule hits: **RUL-002** (name normalized to MDT) and **RUL-003** (2030 capped down to 2025).
- `./ppr gate "st jude 2007"` → **allowed: true**, company **null** (BSX alias not resolved to a canonical code in the gate output), year 2007, **year_capped 2008**, rule hits: **RUL-003** only (2007 capped up to 2008).

Both examples show RUL-003 in action: out-of-range years are adjusted to window bounds, and neither case is hard-denied.

## QUERY_VS_GATE

These are two deliberately separate surfaces:

- **`./ppr query` executes data.** It builds a deterministic tool plan (not a chatbot) and dispatches to statically registered registry tools. Per RUL-001, comparative phrasing routes to `compare_companies` — e.g., the 2023 AbbVie-vs-MDT ICD comparison returns MDT 23 families / 60 models / 918,205 implants vs ABT 10 families / 32 models / 423,440 implants. It does **not** surface a charter policy verdict.
- **`./ppr gate` only inspects policy.** It evaluates the input against charter rules (normalization, year caps, precedence) and returns an allowed/denied verdict with rule hits. It does **not** execute any data query.

In short: query executes data; gate only inspects policy. The two never substitute for each other.

## FAILURE_MODES

1. **Missing charter fails closed** — if the charter is absent entirely, the gate refuses rather than proceeding.
2. **Partial charter parse stays fail-open by policy**, but exposes `partial_charter_parse` / `fallback` diagnostic lines so the degradation is visible, never silent.
3. **Year out of range is not a denial** — 2030 and 2007 illustrate RUL-003's cap-and-warn behavior instead of hard-failing; the risk is silent data-boundary drift, which the `year_capped` field surfaces.
4. **Unresolved company aliases** — as in the "st jude" case, normalization can leave company null; RUL-002 matched names (mdt → MDT) but the st jude spelling did not resolve, so downstream company filtering may be unavailable even though the request is allowed.
5. **Wrong plan selection** — without RUL-001 precedence, comparative requests would silently degrade to generic top-device results, producing data that answers a different question than asked.

Note also: this is an analytical historical registry only — not clinical monitoring, not device programming, and PDF ingestion is offline (not in the live query path), so none of the above failure modes touch patients or implanted devices.
