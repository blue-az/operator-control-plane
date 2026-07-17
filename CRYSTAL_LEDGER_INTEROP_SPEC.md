# Crystal ↔ Ledger Interop — Build Spec

> **Status: DRAFT / proposal.** Dual audience: (a) Erik + Vinh Nguyen (author of
> `@stewie-sh/agent-crystallize` and the PBC spec) as a collaboration proposal; (b) an implementing
> agent once the boundary is agreed. Nothing here is built yet. Upstream schema facts were read
> against `agent-crystallize@0.1.9` source (`src/index.ts`, `renderCrystal`).

**For:** the implementing agent. **Reviewer:** Erik. **Target:** extend the `operator` CLI in this
repo. Match existing conventions (`EXECUTOR_IDENTITY_SPEC.md` remains the identity authority).

---

## 0. Why (the stack, and the trust gap)

PBC already bounds this system **from above**: `owners-manual/pbc/` carries draft behavior
contracts — what the product *should* do — with a draft-until-human-accepted trust model that
matches the ledger's. The **lower** boundary is the GT-KB-derived evidence layer (the Logbook:
"do not trust the narration — verify against the evidence"; see
`project-phoenix/docs/BULKHEAD_TAU_BOUNDARIES.md`). `agent-crystallize` is **not** a boundary —
it is the standard *narration format* arriving AT that boundary: Markdown "checkpoint"
and "crystal" artifacts narrating an agent session's in-flight state (focus, decisions, findings,
open loops, test claims, resume prompt). Untrusted content in a parseable envelope.

The gap: a crystal is **self-narrated and unverified** — mutable Markdown, no hash, no identity
binding, no append-only history. Its `Tests And Verification` section is free text like
`"npm test passed."` — in this repo's vocabulary, that is a *claim*, not truth. Exactly the
narration-vs-execution partition the operator exists to enforce.

So the interop rule is one sentence: **a crystal enters the ledger the way any narration does — as
draft claims and fingerprinted evidence awaiting verification by a distinct identity — never as
verified status.** Operator supplies the integrity layer crystals lack; crystallize supplies the
session-continuity layer the ledger deliberately lacks (session outcome/cost is tracked here, but
nothing helps the *next* session resume).

Composition target: PBC = intent (upper), crystal = session narration (lower), operator = the
enforcement middle that ties both to evidence.

---

## 1. Trust rules (non-negotiable, checked by tests)

- **T1 — One-way read.** Operator reads `.agent-crystals/`; it never writes there. Crystallize
  never touches `.operator/`. File formats are the entire boundary; no code dependency in either
  direction (operator parses crystal Markdown itself — the `agent-crystallize` binary is NOT
  required on the host).
- **T2 — Narration in, never verification in.** No import path may set `verification_status`,
  `verified_by`, or any terminal outcome. Everything extracted from a crystal lands as draft.
- **T3 — Untrusted content.** Crystal text is foreign agent output = prompt-injection surface. The
  `Resume Prompt` fenced block and `Continuity Tail` entries are instructions/transcript aimed at
  *agents*; operator must never execute them, template them into shell commands, or feed them to a
  model. Parse structurally, store bytes, hash them — nothing else. (Same posture as `doctor`
  never executing a stored `--verify-cmd`.)
- **T4 — Identity.** Under enforced policy, attaching/importing a crystal is a **builder** action
  (draft-tier). Verifying claims extracted from it follows the existing distinct-UID verifier
  rules unchanged.
- **T5 — Fingerprint at the boundary.** Crystals are copied into the ledger and fingerprinted
  (SHA-256, byte size, mtime) exactly like other local evidence. The existing doctor fail-closed
  rule for changed verified sources applies with no exemption: if a crystal's bytes drift after a
  claim citing it was verified, doctor fails closed.
- **T6 — Heading uniqueness and canonical ordering.** Operator must validate and enforce structural uniqueness and canonical ordering of recognized headings (from `requiredSections`):
  - `Header` and `Reality Checks` must occur **exactly once**.
  - All other recognized headings must occur **at most once**, and when present, must follow the strict canonical ordering defined in §2.
  - Any file containing duplicate recognized headings or headings that violate the canonical order must be rejected at the boundary as structurally corrupt (exiting non-zero, preventing ledger write), mitigating middle-of-text section forging.
  - Non-security-critical sections that are entirely missing are reported as warnings under P1, not hard rejections.
- **T7 — Independent validation.** Operator must run its own structural validation on crystals
  at the boundary, maintaining its own safety guarantees even if the upstream tool is modified to
  add or fix its validator later.

## 2. Upstream artifact contract (what the parser may assume)

Layout: `.agent-crystals/checkpoints/<timestamp>-<slug>.md` and
`.agent-crystals/sessions/<timestamp>-<slug>.md`; optional `manifest.json` index.

Sections rendered by 0.1.9 (`requiredSections` + extras) in canonical order: Header, Current Focus,
Durable Framing, Checkpoint Trail, (optional Continuity Tail), Topics, Relation Hints, Session
Provenance, Decisions, Findings, Reality Checks, Artifacts Changed (Git Status / Diff Stat /
Changed Files / Instruction Files Present / Evidence Pointers), Tests And Verification, Open Loops,
Memory Candidates, Next Actions, Resume Prompt.

Header bullets: `Scope`, `Project`, `Source window`, `Budget`, `Surface`, `Repo`,
`Observed at` (ISO-8601). Reality Checks carries `Git commit` / `Git branch` / `Git root`.

**Defensive-parsing rules (upstream schema is explicitly draft — their STATUS.md says so):**

- P1: Unknown sections are ignored; a missing expected section is a per-file `[Warning]` in
  operator output, never a crash or a partial-write.
- P2: Empty sections contain fallback boilerplate, not emptiness (e.g. *"No separate verification
  captured for this artifact."*, *"(none provided)"*). The parser must recognize the 0.1.9
  fallback strings and treat those sections as empty — importing boilerplate as a claim is a bug.
- P3: Pin the recognized-section list and fallback strings in one module-level table with the
  upstream version noted, so a schema bump is a one-table diff.
- P4: No AGENTS.md metadata lookup. Do not attempt to parse `AGENTS.md` to resolve metadata
  (like the project name or path). `AGENTS.md` is agent/human instruction guidance and is not a
  stable machine database. All machine-readable schema and project metadata must be read from the
  crystal Header itself, a schema-versioned `manifest.json` field, or a dedicated `.agent-crystals`
  metadata file.

## 3. Shared relation vocabulary (zero code, both sides — do this first)

Crystallize already supports free-form `--relation "type:target"`. Reserve:

| relation | written by | meaning |
| --- | --- | --- |
| `operator-task:<task-id>` | agent, in the crystal | this session's work belongs to ledger task |
| `operator-claim:<claim-id>` | agent, in the crystal | narration relevant to a specific claim |

Operator side: nothing to build in this phase — the tokens exist so later phases (and humans) can
correlate. This is a documented convention, same shape as the PBC collaboration: agree on format,
ship nothing.

## 4. Schema change

Add one evidence type: `session_crystal` (alongside `run_log, manifest, …, external_doc`). A
crystal is neither a transcript nor raw tool output — it is narrated summary, and the distinct
type lets doctor and humans treat it at the right trust altitude.

## 5. Commands

### 5.1 `crystal-attach PATH --claim CID [--by WHO]` (Phase 1)

Sugar over the existing `evidence-attach` path with `--type session_crystal`, plus crystal-aware
metadata capture at attach time:

- copy + fingerprint per T5 (missing path rejected, `--hash` precheck honored, unchanged);
- parse the Header / Reality Checks and record alongside the evidence entry:
  `crystal_kind` (checkpoint|session, from path or Source window), `crystal_project`,
  `crystal_observed_at`, `crystal_source_commit`, `crystal_source_branch`;
- no `--status` accepted on this command at all (T2 — verification goes through the normal
  `evidence-attach --status` flow by a distinct verifier, citing the already-attached artifact).

### 5.2 `crystal-import PATH [--task ID] [--open-loops-as-tasks] [--by WHO]` (Phase 2)

Extraction, always draft-tier:

- `Tests And Verification` bullets → one **draft `test_passes` claim each**, text prefixed
  `[crystal-narrated]`, with the crystal auto-attached via 5.1 as their initial (status-less)
  evidence;
- `Open Loops` bullets → new tasks **only** under `--open-loops-as-tasks` (default off; open
  loops are often stale);
- `Decisions` / `Findings` / `Memory Candidates` → **not extracted** (recorded only as the
  attached artifact's content; deciding their claim types is future work, not Phase 2);
- `Resume Prompt` / `Continuity Tail` → never extracted (T3);
- idempotency: re-importing the same crystal fingerprint is a no-op with a notice, not duplicate
  claims.

## 6. Doctor rules (added — all advisory; crystals are foreign artifacts)

For each `session_crystal` evidence entry:

- `crystal_source_commit` recorded but not found in the target repo's history →
  **`[Warning]` crystal cites unknown commit '<sha>'** (provenance drift or wrong repo).
- crystal narrates ≥1 test bullet (post-P2 fallback filtering) and no claim in the ledger cites
  this crystal → **`[Info]` crystal narrates N verification claims; none registered** — the
  narration-vs-ledger gap made visible.
- claims extracted by `crystal-import` follow the existing unverified/self-verified/advisory
  reporting with no special casing (they are ordinary draft claims).
- byte-drift on a crystal cited by a verified claim → existing fail-closed rule, no new code.

Doctor never renders crystal body text into its own output beyond first-line excerpts (T3).

## 7. Tests (`tests/`, subprocess style; fixtures = synthetic crystals only)

Add `tests/fixtures/crystals/` with hand-written 0.1.9-shaped fixtures (never real dogfood
artifacts — same hygiene as upstream's `examples/`):

1. **attach + fingerprint:** `crystal-attach` a fixture → evidence recorded as `session_crystal`,
   SHA-256 matches, header metadata captured.
2. **no status laundering:** `crystal-attach --status verified` (or any status) → exits non-zero;
   claim untouched. (T2)
3. **duplicate or out-of-order headings rejected:** `crystal-attach` a fixture containing duplicate
   recognized headings (e.g. duplicate `## Decisions` in body) or out-of-order recognized headings
   (violating layout order in §2) → exits non-zero, rejects attachment before any ledger write. (T6)
4. **import extracts real bullets only:** fixture with 2 test bullets + fallback-string sections →
   exactly 2 draft `test_passes` claims; Decisions/Resume Prompt content appears in no claim text.
   (P2, T3)
5. **import idempotent:** second `crystal-import` of same file → no new claims, notice printed.
6. **doctor unknown-commit warning:** fixture citing sha `deadbeef` → `[Warning]`, exit 0
   (advisory).
7. **doctor drift fail-closed:** verify an extracted claim properly (distinct `--verified-by`),
   then mutate the attached crystal copy's source → doctor exit 1.
8. Existing `tests/test_operator.py` still passes; live-ledger `doctor` unaffected.

## 8. Phases

- **Phase 1** (smallest reviewable unit): §4 evidence type + §5.1 `crystal-attach` + §6 doctor
  rules 1–2 + tests 1, 2, 3, 6. Local-lane candidate per `LOCAL_LANE_CONTRACT_SPEC.md` — the parser
  table (P3) makes it plan-shaped.
- **Phase 2:** §5.2 `crystal-import` + tests 4, 5, 7.
- **Phase 3** (only if Phases 1–2 prove useful in dogfood): hook/session bridging — crystallize's
  hook runner fires SessionStart/PreCompact/Stop; a thin wrapper opens `session-start` on
  SessionStart and attaches the rolled-up session crystal at `session-end`. Separate mini-spec
  when reached; not designed here.

## 9. Upstream asks (Vinh — all non-blocking; the spec works against 0.1.9 as-is)

1. A stable Header field for external ledger references (so `operator-task:` links live in the
   header, not free-text relations) — his artifact schema is still draft; now is the window.
2. A schema-version marker in the Header, so P3's pinned table can key on it instead of sniffing.
3. (Nice-to-have) a documented "finalized" convention distinguishing a closed session crystal from
   one still being appended to — sharpens the T5 drift rule's intent.

## 10. Exclusions

- No hosted/sync/Stewie-service dependency in either direction; both tools stay local-file-only.
- No execution or model-ingestion of any crystal content, ever (T3) — including in future phases.
- No auto-verification, no backfill of verification from crystal text, however confident the
  narration sounds.
- No operator writes into `.agent-crystals/` (T1); a future "export ledger state as a crystal" is
  explicitly out of scope until Vinh has weighed in.

---
*Continues the boundary-composition lane: PBC (upper, merged — pbc-spec PR #6) → operator
(enforcement) → GT-KB-derived Logbook (lower); crystals are the narration format at the lower
boundary (this spec). Surfaced by the 2026-07-15 agent-crystallize evaluation session; taxonomy
corrected 2026-07-17 (see BOTTLENECKS boundary-drift entry).*
