# PPR Agent benchmark gold standard (v1)

Typed gold standard for `evals/ppr_agent_benchmark`. Two lanes, explicitly
separated. Results from the lanes must never be merged in claims.

Lane A claims grounded reproduction only; Lane B is the only execution-competence lane.

## Lanes (do not merge)

| Lane | What is under test | What a score may claim | What a score must not claim |
|---|---|---|---|
| **A** | Grounded reproduction of a frozen packet into three fixed-heading briefs | Grounded fact retrieval and format adherence ONLY | Tool use, database execution, gate execution, or PPR CLI competence |
| **B** | Live deterministic execution of recorded `./ppr` commands against `/home/blueaz/Python/ppr-agent` | PPR tool, DB, and gate competence (this lane only) | Anything about free-text brief writing or packet regurgitation |

Machine-checkable expected values live in `manifests/gold_manifest_v1.json`.
The typed checker is `check_run.py`.

## Frozen packet (both lanes)

Lane A is given `sources/ppr_ground_truth.md` plus the exact repo facts below.
Lane B does not read that packet; it must run the CLI against the frozen database.

| Input | Role | Value at this freeze |
|---|---|---|
| `ppr_agent.db` SHA-256 | Full deterministic registry | `753123e5d05de9008d6ddfdfa813a214cdfc5df1241fe8f2156b3f81974daf89` |
| `PPR_Agent.pbc.md` SHA-256 | Charter rules | `6cdbb3fb47dbd971269d0d5fb5ff3d37831c7f7f72f3f9b543bc1ba3bc7db359` |
| `desk/devices_published.json` SHA-256 | Published Desk subset | `1fae1b6b3dea55d98aefb3f63386cab7df43f7716b6db2275bfa579ac7c1d09c` |
| ppr-agent HEAD | Source lineage at authoring | `04ed8ed9ce8095cbeedc09d5aa218e7ffb2565ad` |
| Observed date | Freeze day | 2026-09-03 |

Do not substitute a live web result or an unpinned database. A changed DB, PBC,
or tool implementation is a new gold-standard version.

---

# Lane A (grounded reproduction)

Claims: grounded fact retrieval + format adherence ONLY. No claim of tool, DB, or gate execution.

Given the frozen packet, produce the three task briefs below with exact facts
and the required section headings. Scoring is case-insensitive substring
presence, with numbers comma-tolerant (`3576` matches `3,576`).

This lane does not run `./ppr`. A fluent brief that copies packet facts is a
Lane A success. It is not evidence that the model queried the registry.

## Task `ppr1_product_boundary`

Write a concise product-boundary briefing. Preserve exact facts. Avoid overclaiming.

**Required headings (exact strings):** `SURFACES`, `DATA_BOUNDARY`, `NON_GOALS`, `NUMBERS`, `RISK_NOTES`.

**Required facts (all must appear):**

- Four surfaces: Registry tools, CLI `./ppr`, Charter/PBC, Analyst Desk.
- Tool catalog: 15 tools.
- Full registry: 3576 device models (packet also writes 3,576).
- Desk published subset: 1483 devices (packet also writes 1,483).
- Published is 41.5% of full.
- Analytical historical registry only; not clinical monitoring; not device programming.
- PDF extraction is offline ingestion, not part of the live query path.
- Natural-language query is deterministic plan-building/tool dispatch, not a chatbot or free-text LLM assistant.

**Forbidden overclaims (must all be absent):** clinical-advice directives, live patient monitoring claims, chatbot self-identification, invented stale counts such as 2374 device models.

## Task `ppr2_gate_query_semantics`

Explain query/gate semantics and answer the two gate examples from the packet.

**Required headings:** `RULES`, `GATE_RESULTS`, `QUERY_VS_GATE`, `FAILURE_MODES`.

**Required facts:**

- PPR-RUL-001 / RUL-001: pattern precedence; comparative queries before generic top-device plans.
- PPR-RUL-002 / RUL-002: company code normalization to ABT / BSX / MDT.
- PPR-RUL-003 / RUL-003: years outside 2008-2025 warn or cap; a year alone does not hard-deny.
- `mdt 2030`: allowed true, company MDT, year 2030, year_capped 2025, rule hits RUL-002 and RUL-003.
- `st jude 2007`: allowed true, company null, year 2007, year_capped 2008, rule hit RUL-003.
- `./ppr query` executes deterministic tool plans and does not surface a charter policy verdict.
- `./ppr gate` inspects policy and does not execute data queries.
- Missing charter fails closed. Partial charter parse remains fail-open by policy but exposes `partial_charter_parse` / fallback lines.

**Forbidden overclaims:** same class as ppr1; also claiming that an out-of-range year is hard-denied, or that `st jude` normalizes to Abbott.

These gate numbers are packet facts for Lane A. Reciting them is not a Lane B gate-execution claim.

## Task `ppr3_real_data_report`

Produce an analyst report from the packet's real-data facts.

**Required headings:** `ICD_2023_COMPARISON`, `TOP_2023_DEVICES`, `MARKET_CONCENTRATION`, `SCOPE_LIMITS`.

**Required facts:**

- ICD 2023 comparison (compare_companies in the packet): MDT 23 families / 60 models / 918205 implants; ABT 10 families / 32 models / 423440 implants.
- Top five 2023 devices: Azure XT DR W1DR01 623926; Adapta DR ADDR01 454869; PM2272 383089; Advisa DR MRI A2DR01 344410; ACCOLADE/PROPONENT/ESSENTIO 278000.
- ICD 2023 concentration: HHI 3912.31, level High, shares MDT 52.96, ABT 24.42, BSX 22.61.
- Scope: historical analytical registry data, not clinical advice.

**Forbidden overclaims:** clinical advice, live monitoring, chatbot framing, invented counts.

---

# Lane B (live deterministic execution)

The model (or an agent with tools) must run recorded `./ppr` commands against
`/home/blueaz/Python/ppr-agent` and return the exact JSON fields listed in the
manifest. Only this lane may claim PPR tool/DB/gate competence.

Working directory for every command: `/home/blueaz/Python/ppr-agent`.
Timeout: 60 seconds. Non-zero process exit or any field mismatch fails the entry.
Numbers compare as numbers. HHI compares as float with tolerance 0.01.
`rule_hits` compares as a set: actual must be a superset of expected.

Commands below were executed read-only on 2026-09-03 against HEAD
`04ed8ed9ce8095cbeedc09d5aa218e7ffb2565ad` and the pinned `ppr_agent.db` hash.
Do not treat this section as a Lane A briefing key.

## `./ppr stats`

Overview: `total_devices` 3576, `total_implants` 92071191, `earliest_year` 2008,
`latest_year` 2025, `years_count` 18, `companies_count` 3.

By company: MDT 1892 devices / 48343280 implants; ABT 1271 / 29111911; BSX 413 / 14616000.

## `./ppr tools`

Exactly 15 tools. Name list (registry order):

1. `get_top_devices`
2. `get_market_share_trend`
3. `compare_companies`
4. `get_device_longevity`
5. `get_year_over_year_growth`
6. `search_devices`
7. `get_database_stats`
8. `get_category_breakdown`
9. `get_company_portfolio`
10. `get_growth_leaders`
11. `get_market_concentration`
12. `get_device_lifecycle`
13. `get_competitive_positioning`
14. `show_capabilities`
15. `export_results`

`./ppr tools` prints a text catalog, not JSON. The checker parses the listing.

## `./ppr gate 'mdt 2030'`

`allowed` true, `company` MDT, `year` 2030, `year_capped` 2025.
`rule_hits` is a superset of `PPR-RUL-002` and `PPR-RUL-003`.

## `./ppr gate 'st jude 2007'`

`allowed` true, `company` null, `year` 2007, `year_capped` 2008.
`rule_hits` contains `PPR-RUL-003`. The charter alias set does not map
`st jude` to ABT.

## `./ppr query 'compare Abbott and Medtronic ICDs 2023'`

Plan tool: `compare_companies` (not generic top-devices).
ICD 2023: MDT 23 families / 60 models / 918205 implants; ABT 10 / 32 / 423440.

## `./ppr run get_top_devices --year 2023 --limit 5`

- Rank 1: Azure XT DR W1DR01, 623926 implants.
- Rank 2: Adapta DR ADDR01, 454869 implants.
- Rank 3: PM2272, 383089 implants.
- Rank 5: 278000 implants (BSX ACCOLADE/PROPONENT/ESSENTIO DR family).

## `./ppr run get_market_concentration --year 2023 --device-category ICD`

HHI 3912.31, level High, shares MDT 52.96, ABT 24.42, BSX 22.61.

---

# Checker

```bash
python3 check_run.py <run_dir>              # Lane A rescore (no write)
python3 check_run.py <run_dir> --write      # also write scores_strict.json in the run dir
python3 check_run.py --lane-b               # execute Lane B against ppr-agent
python3 check_run.py --lane-b --only ppr_stats,ppr_tools
```

Lane A requires `manifest.json` in the run dir. For OpenAI-compatible
`raw_response`, content is `choices[0].message.content`. Empty content with
`reasoning_content` present fails the run with reason
`finish_reason_length_or_reasoning_only` (regression for the 0/28 FreeToken
run `runs/20260826-204632`). `--write` never overwrites `scores.json` or
`SCORES.md`. Exit 0 if fully pass, 2 otherwise.

Lane B is the only path that executes `./ppr`.

# Known drift (document only; do not fix in ppr-agent)

These are source comments/paths that disagree with the frozen database.
The gold standard uses live `./ppr` / SQLite facts, not the stale comments.

1. `core/data_client.py` module docstring says `2,374 devices, 2008-2024`.
   Actual frozen registry: 3576 devices, 2008-2025.
2. `schema.sql` comment on `year` says `Report year (2008-2022)`.
   Actual year range: 2008-2025 (18 distinct years).
3. `desk/extract_devices.py` hardcodes
   `/home/blueaz/Python/project-phoenix/domains/PPR_Agent/ppr_agent.db`
   and a project-phoenix `bulkhead-factory` output path. That is a stale
   Phoenix path; the standalone extract uses `/home/blueaz/Python/ppr-agent/ppr_agent.db`.

Do not "correct" these in the ppr-agent repo as part of this freeze.

# Acceptance

- Lane A pass: every result has `returncode == 0`, non-empty extracted
  content, every required heading and required value present, every
  forbidden value absent. That pass is grounded reproduction only.
- Lane B pass: every recorded command exits 0 and every expected field
  matches. That pass is execution competence.
- Never add a Lane A score to a Lane B total, or the reverse.
- Historical `runs/` are baselines for the Lane A checker, not new gold data.
- Existing regex `score_run.py` remains a compatibility report. It is not
  this gold standard.
