SURFACES
Registry tools, CLI `./ppr`, Charter/PBC, Analyst Desk.

DATA_BOUNDARY
Standalone source-legible extract of PPR_Agent CRM domain, not the full Phoenix system. Analytical historical registry only; not clinical monitoring or device programming. PDF extraction is offline ingestion; not part of live query path. Natural-language query is deterministic plan-building/tool dispatch; not a chatbot/free-text LLM assistant.

NON_GOALS
Not clinical monitoring. Not device programming. Not live query path for PDF ingestion. Not a chatbot or free-text LLM assistant.

NUMBERS
Tool catalog: 15 statically registered tools. Full registry: 3576 device models, 92,071,191 registered US implants (2008-2025, 18 years, 3 companies). Desk published subset: 1483 devices; full devices.json: 3576 devices; published is 41.5% of full.

RISK_NOTES
Missing charter fails closed. Partial charter parse remains fail-open by policy but exposes partial_charter_parse/fallback lines. `./ppr query` executes deterministic tool plans and does not surface a charter policy verdict; `./ppr gate` inspects policy and does not execute data queries.