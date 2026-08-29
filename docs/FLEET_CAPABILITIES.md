# Six fleet capabilities, and what this repo does about each

A multi-agent "fleet harness" is usually pitched as six capabilities. This document
answers each one for `operator-control-plane` — covered, deliberately refused, or
missing — with the file that decides it. Where the answer is "no," the reason is
here rather than in a spec you would have to go find.

**The short version.** Five of the six are *capability* questions: can the fleet do
X. This repo answers a different question — **is what an agent says it did true, and
did a different identity check?** Those are complementary, not competing. A fleet
that does all six and cannot answer that question is a faster way to produce
unverified claims. A ledger that answers it and cannot dispatch anything is a filing
cabinet. Most of what follows is about which half this is.

| # | Capability | Status |
|---|---|---|
| 1 | Treat Claude Code / Codex / dsh / OpenCode as options | **Covered**, with gaps |
| 2 | Sessions talk to each other | **Covered, deliberately indirect** |
| 3 | Sessions talk across machines | **Covered** — records yes, messaging yes, ledger *distribution* refused |
| 4 | Sessions talk across harnesses | **Covered** — and load-bearing for the trust model |
| 5 | Fork (copy\|move) sessions across machines | **Refused by construction** |
| 6 | Missions have memory; the Fleet has memory | **Mission: yes. Fleet: refused** |

---

## 1. Treat Claude Code / Codex / dsh / OpenCode as options

**Covered, with two gaps.**

`harness_adapter.py` holds a `PROFILES` table — `claude`, `agy`, `codex`, `grok`,
`opencode` — each with its executable, a frozen `--version` check, prompt transport,
role, and the per-harness flags that mean the same thing under different names
(`--permission-mode` vs `-s workspace-write` vs `--auto`). `operator init` seeds a
harness registry under `.operator/harnesses/*.yaml` covering those plus `copilot`,
`fable`, `openrouter`, and the local-model seats.

The framing differs from a fleet's, though, and the difference matters. A fleet
treats harnesses as interchangeable **runtimes** — swap the engine, same job. This
ledger treats them as **identities that make claims**. `assigned_harness`,
`review_harness`, `harness_id` and `lane` are routing, provenance and economics
fields. They confer nothing: see `AGENTS.md`, "Harness roles are not ranks." Nothing
here infers that Claude is the supervisor and a local 26B is the builder from brand
name. What the harness id is *for* is answering "who claimed this" later.

**Gaps, stated plainly:** there is no `dsh` profile. `dsh` is DeepSeek Harness,
DeepSeek AI's plugin-first agent runtime (MIT, released 2026-08-13), in which the model
adapter, tool registry, session log and the agent loop itself are all swappable plugins.
Base `dsh` has no interactive CLI — the Claude Code-style terminal surface comes from
`dsh-tui`, an out-of-tree plugin bundle, or from a separate CLI-focused fork. So "dsh"
names at least three invocations, and a profile asserting flags nobody confirmed would
be worse than its absence: every flag in this table was checked against that CLI's own
`--help`, which is the only reason the table is worth anything.

`pi` was the other gap and is now closed: `ed22df8` made pi the implementer carrier on
2026-08-27 and migrated the ladder runner, but left the adapter behind, so dispatch to
pi had to bypass it. The profile now exists, with flags confirmed against `pi --help`
at v0.84.4, and it declares no workspace flag because pi genuinely has none — the
sandbox boundary is the caller's responsibility, and claiming otherwise would be a
false guarantee. `--plan` is deliberately not claimed: pi's own help notes it comes
from a plan-mode extension, not the core CLI.

## 2. Sessions talk to each other

**Covered, and deliberately routed through a record rather than a socket.**

Two mechanisms, both in the ledger:

- `handoff-add` — a structured closeout: what changed, what was verified, what is
  claimed, what remains open, next action.
- `export-brief --for <harness>` — a brief generated *for* the receiving harness from
  ledger state.

That indirection is a decision, not a missing feature. `docs/specs/ROLE_SCOPED_BRIEF_SPEC.md`
records why: brief output containing builder-authored text meant "a reviewer would
read the builder's narrative before forming an independent verdict," which created
anchoring risk and weakened the cross-audit boundary. A live session-to-session
channel is that anchoring risk with no filter at all. So sessions talk, but through
something a third party can read afterward.

**What is genuinely absent:** notification. A receiving session is not woken. It
learns there is something for it when a human says so, or when it checks.

## 3. Sessions talk across machines

**Covered — but "cross-machine" is three different things, and conflating them is
why this question keeps reopening.** Splitting them first, then answering each:

| | What it means | Status |
|---|---|---|
| **Records** | a record knows which machine produced it | **Built** |
| **Messaging** | a session on one box reaches a session on another | **Works, deliberately outside this repo** |
| **Distribution** | two machines share one ledger and reconcile | **Refused** |

**Records — built, and first-class.** Every record carries `executor.machine`,
stamped by `get_machine_identity()` (`OPERATOR_MACHINE` override → short hostname →
`"unknown"`). Work produced elsewhere is not second-class: `usage-import --source-dir
PATH --machine NAME` labels imported records with the **producer** machine rather than
the importer, and `usage-summary --by-machine` groups runs, cost and tokens by machine
× harness. So the ledger has always been able to say "z13 did this, and it cost that."

**Messaging — works, and is intentionally not in this repo.** ssh already reaches every
box; a message is a file drop plus a carrier. That carrier is versioned in the
operator's dotfiles, not here, because a message bus is machine infrastructure and this
is a ledger — the same boundary `AUTHORITY_BROKER_SPEC.md` draws for the broker.
Nothing about it needs ledger authority: when a background machine needs to record
something at the seat, the right move is to write to *the seat's* ledger over ssh, not
to open one locally.

**Distribution — refused, and since 2026-08-29 enforced rather than merely documented.**
`docs/specs/MACHINE_PROVENANCE_SPEC.md`: "Multi-machine support is therefore
**provenance, not distribution**." Record ids are sequential (`claim-0001`), so two
stores that both allocated `claim-0042` cannot merge without rewriting an append-only
history. The rule existed in prose for months and was violated continuously — one
background machine had accumulated two parallel ledgers, because `operator init` simply
worked there and nothing checked. `docs/specs/MACHINE_ROLE_ENFORCEMENT_SPEC.md` closed
it: `operator.yaml` carries `role: seat|outbox` and `seat_machine`, and `doctor` fails
closed when a seat store is opened on a machine that is not the seat.

**So the honest answer to the bullet as written** — *allow sessions to talk across
machines* — is yes, and it has been all along. What is refused is the thing the bullet
does not actually ask for: making every machine authoritative.

## 4. Sessions talk across harnesses

**Covered — and this one is not a convenience feature, it is the trust model.**

Cross-harness handoff works through the same brief and handoff records as §2, with
`--for <harness>` shaping the output. But the reason it matters here is different
from a fleet's. In this repo, a claim made by one harness and verified by another is
the *only* way verification means anything:

- `evidence-attach --status` requires `--claim` (fail-closed).
- Trusted verification requires a **distinct OS UID**, not a different harness name.
  A status is recorded as `uid_isolated` only when the registered verifier UID differs
  from the claim's recorded author UID (`docs/specs/EXECUTOR_IDENTITY_SPEC.md`,
  `docs/specs/VERIFIED_BY_GUARD_SPEC.md`).
- Same-UID verification still works and is explicitly recorded as `advisory`. No
  self-grading, and nothing is silently upgraded.

So "across harnesses" is necessary but not sufficient here. Two harnesses run by the
same Unix user are, to this ledger, one identity.

## 5. Fork (copy | move) sessions across machines

**Refused by construction, for two independent reasons.**

First, IDs. Record ids are sequential and zero-padded — `claim-0001`, `evidence-0001`.
Two stores that both allocated `claim-0042` cannot be merged without rewriting one,
and rewriting an append-only history defeats its purpose. `MACHINE_PROVENANCE_SPEC`
is blunt about it: never `operator init` a second ledger for the same work, and **the
seat does not move.** Travel widens the ingest lag; it is not a seat handoff.

Second, and less obvious: **identity does not survive the hop.** UID isolation is
kernel-attested and machine-local. `uid 1000` on one box and `uid 1000` on another are
unrelated principals. Fork a session across machines and the work arrives intact while
every trust claim about it silently degrades to advisory — which is worse than not
moving it, because nothing looks wrong.

The missing piece for anyone who wants this is signed, scope-narrowing delegation —
proving *which human authorized which agent for what*, portably. `AUTHORITY_BROKER_SPEC.md`
excludes "remote transport, signatures/keys" from its scope deliberately. That is the
honest boundary: this repo proves **execution** identity and stops at the machine edge;
a signature-based scheme proves **authorization** and travels. Each is the other's
blind spot — a key holder can sign a claim about work it never did.

## 6. Missions have memory, and the Fleet as a whole has memory

**Mission memory: yes, and it is the whole point. Fleet memory: refused.**

The ledger *is* mission memory, but a different kind than a fleet usually means. Not
"what did we discuss" — that is context, and context is narration. This stores what
was claimed, what evidence backed it, who verified it under which identity, what it
cost, and what remains open. YAML projections under `.operator/` are the current view;
`.operator/ledger.sqlite3` keeps immutable full-snapshot versions of every
trust-relevant write, and `doctor` fails closed when the two disagree.

Fleet-wide memory is the §3 and §5 problem wearing a different hat: shared mutable
state across machines, reconciled later. Same merge hazard, same refusal.

---

## What this does not do

Stated here so it does not have to be discovered:

- **It does not run your agents.** `gated_runner.py` enforces a postcondition around
  a run and `study_runner.py` executes typed resumable plans, but there is no fleet
  scheduler and no session supervisor.
- **`doctor` never executes a stored `verification_command`.** It is read-only and
  structural by design. A `--verify-cmd` is inert audit metadata, even for a
  UID-isolated verifier.
- **Structural validity is not semantic truth.** A vacuous gate (`assert True`) or a
  hash of irrelevant bytes can look perfectly valid. Whether evidence proves the claim
  remains a reviewer's judgment. See the README's "Known limitations."
- **The repo-local policy gate is self-amendable.** An agent with write access to
  `.operator/identity.yaml` can weaken the gate binding it.

If those four are unacceptable for your use, this is the wrong tool, and that is a
better thing to learn from a README than from a ledger you already trusted.
