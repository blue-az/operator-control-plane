## What operator Is For

_operator is a local command-line control plane with a file-backed ledger under .operator/. Its job is not to be a general project tracker or a hosted control plane; it is to keep multi-agent work legible through a task, claim, evidence, and verification frame. For the owner, the important thing is the boundary: this product is about preserving accountable work records inside a bounded local workflow._

### One-Minute Snapshot

operator is a local command-line control plane with a file-backed ledger under .operator/. Its job is not to be a general project tracker or a hosted control plane; it is to keep multi-agent work legible through a task, claim, evidence, and verification frame.

For the owner, the important thing is the boundary: this product is about preserving accountable work records inside a bounded local workflow. The human operator maintains the ledger, assigned harnesses do the work, review harnesses check it, and verifiers are recorded when trust changes. The next chapters go deeper into the lifecycle, the records, and the verification rules; this chapter only sets the identity and the limits.

> **Figure:** The owner should read operator as a local control surface over a bounded ledger, so the product ends at the recorded workflow instead of expanding into a hosted control plane or a generic tracker.

```mermaid
flowchart TD
  O[Owner]
  subgraph B[Local product boundary]
    C[Fixed command surface]
    L[File-backed local ledger]
    W[Recorded task, claim, evidence, verification flow]
    C --> L --> W
  end
  X[Outside the product]
  O --> C
  X -. not part of the product .-> C
```

This diagram shows the owner using a local product boundary that contains a fixed command surface, a file-backed local ledger, and the recorded task-to-claim-to-evidence-to-verification flow. Anything outside that boundary is not part of the product's scope.

### What You Should Be Able To Explain

- Understand that operator is a local CLI plus a .operator/ ledger, not a hosted SaaS control plane.
- Recognize the native roles: operator, assigned harness, review harness, and verifier.
- See the core product frame: task, claim, evidence, then verification.
- Know that brief and handoff records are the continuity path between harnesses.
- Notice the main boundary risks before deciding what to trust or correct.

### Mental Model

The owner should read operator as a local governance ledger for software work. The product matters because it turns scattered multi-agent activity into a recorded sequence: work is assigned as a task, assertions become claims, claims are supported by evidence, and trust changes only through verification. That is the load-bearing frame of the product, and it is the reason the manual keeps returning to the same vocabulary instead of treating this as generic ticket tracking.

This chapter stays at the level of identity and boundary. The detailed movement of work through the ledger belongs in the lifecycle chapter, and the mechanics of records belong in the surfaces chapter.

> **Figure:** Continuity is not informal memory here. The next harness starts from recorded context, so the handoff path keeps work legible across role changes instead of forcing a cold restart.

```mermaid
sequenceDiagram
  participant Current as Current harness
  participant Ledger as Local ledger
  participant Next as Next harness
  Current->>Ledger: Record the brief and handoff
  Current->>Ledger: Close the session
  Ledger-->>Next: Surface the latest handoff and next action
  Next->>Ledger: Continue from the recorded context
```

The current harness writes the brief and handoff into the local ledger, then closes the session. The next harness reads that recorded context and continues from the latest handoff and next action. The consequence is that work moves forward through saved records rather than through memory alone.

### How It Works

The executable surface is a fixed CLI, and the durable surface is the .operator/ ledger. Some write commands bind to the current task when the task is not passed explicitly, so the product expects there to be an active piece of work already in view. A new claim begins unverified and linked to its task; it does not become trusted just because it exists.

Briefs and handoffs are the continuity layer between harnesses. Sessions, usage, and provenance records support the work, but they do not replace the core task-to-claim-to-evidence-to-verification sequence. That keeps the product centered on accountable work records rather than on a generic activity log.

> **Figure:** Convenience comes with a dependency: if the task is omitted, the write falls back to the current ledger state, so the command is only safe when the active task is already set.

```mermaid
flowchart LR
  subgraph A[With an explicit task]
    A1[Writer names the task]
    A2[The write targets that task]
    A1 --> A2
  end
  subgraph B[Without an explicit task]
    B1[Writer omits the task]
    B2[The product reads the current task]
    B3[No active task exists]
    B4[The write fails closed]
    B1 --> B2 --> B4
    B2 -. when nothing is active .-> B3 --> B4
  end
```

With an explicit task, the writer points the command at a known target and the write goes there directly. Without an explicit task, the product tries to use the current task from the ledger; if no active task exists, the write stops instead of guessing. The consequence is that these writes depend on existing task state when the task is not named.

### Verified Facts

- The CLI surface is statically enumerated, not dynamically discovered.
- The first run creates the standard .operator/ structure, and rerunning bootstrap does not repair a tree that already exists.
- Several task-bound writes fall back to the current task when no task is supplied, and they fail closed if no active task exists.
- Claims start unverified, with no verifier and no evidence refs, then link back to the task that owns them.
- Briefs and handoffs are designed to carry context forward to the next harness.
- Operational writes record executor provenance, while doctor acts as a diagnostic check for identity and drift rather than the product's main identity.

> **Figure:** A claim does not become trusted just because it exists, and closeout is not final if quarantine comes later. The owner should treat the terminal state as reversible when that later signal appears.

```mermaid
stateDiagram-v2
  [*] --> Unverified
  state "Claim unverified" as Unverified
  state "Verification gate" as Gate
  state "Claim verified" as Verified
  state "Task closeout" as Closed
  state "Quarantined" as Quarantined
  Unverified --> Gate: evidence is attached
  Gate --> Verified: verifier accepts
  Gate --> Unverified: verifier is missing or mismatched
  Verified --> Closed: the task reaches closeout
  Verified --> Quarantined: quarantine arrives earlier
  Closed --> Quarantined: quarantine can still overwrite it
```

A claim starts unverified. When evidence is attached, it enters a verification gate; if the verifier is accepted, the claim becomes verified, and if the verifier is missing or mismatched, it stays unverified. When the task reaches closeout, a later quarantine can still overwrite that terminal state. The consequence is that trust is gated, and terminal status is not one-way.

### Strengths

The strongest thing about the product is that it makes work legible across harnesses without asking the owner to trust memory. The vocabulary is consistent across the command surface and the recorded workflow, which makes it easier to tell whether a task is actually supported, merely asserted, or already verified.

A second strength is that the product keeps continuity explicit. Briefs, handoffs, sessions, and provenance are recorded as part of the workflow instead of being left as informal side notes, so the ledger can answer what happened and who acted even when the work moved between roles.

### Attention Cards

#### ⚠ This may be only the local tool, not the whole workflow  _(attention · critical)_

**What happens:** The evidence supports a bounded local product, but it does not prove that this repository covers every surrounding process the owner uses.

**Why it matters:** If later evidence shows external companion steps, the manual must keep the boundary explicit instead of implying that operator is the entire operating system for the business.

**What to do:** Review this boundary and decide whether the current behavior is intentional.

**Revisit when:** When product identity behavior or related owner decisions change.

#### ⚠ Init does not repair a broken ledger tree  _(attention · high)_

**What happens:** First-run setup creates the standard .operator/ structure, but an already existing .operator/ stops bootstrap from rebuilding missing pieces.

**Why it matters:** A partial or damaged ledger will not be fixed by rerunning bootstrap, so the owner should treat setup as creation, not repair.

**What to do:** Review this boundary and decide whether the current behavior is intentional.

**Revisit when:** When product identity behavior or related owner decisions change.

#### ⚠ Some writes depend on the current task already being set  _(attention · high)_

**What happens:** Several task-bound commands use the current task when no task is supplied and fail closed when there is no active task.

**Why it matters:** This is convenient when the workflow is already anchored, but it can surprise an operator who expects every write to stand alone without repository state.

**What to do:** Review this boundary and decide whether the current behavior is intentional.

**Revisit when:** When product identity behavior or related owner decisions change.

#### ⚠ A claim is not trusted when it is created  _(attention · medium)_

**What happens:** A new claim starts unverified, with no verifier and no evidence refs.

**Why it matters:** The owner should not read claim creation as correctness; it is only a tracked assertion that still needs support and verification.

**What to do:** Review this boundary and decide whether the current behavior is intentional.

**Revisit when:** When product identity behavior or related owner decisions change.

### Owner Decisions

#### ⚖ Should this manual treat operator as the whole operating environment, or as one local component inside a larger workflow?  _(owner decision · open)_

**Why it matters:** That choice controls how far the manual is allowed to generalize beyond the repository evidence.

**Revisit when:** Before changing the related product identity behavior.

#### ⚖ Should task-bound writes rely on the current task by default, or should every write require an explicit task selection?  _(owner decision · open)_

**Why it matters:** The current fallback is useful, but it makes the product depend on existing ledger state.

**Revisit when:** Before changing the related product identity behavior.

#### ⚖ Should bootstrap stay a first-run setup step, or should it also repair an existing .operator/ tree?  _(owner decision · open)_

**Why it matters:** The answer determines whether a partially initialized ledger is an expected maintenance case or a supported recovery path.

**Revisit when:** Before changing the related product identity behavior.

### Evidence Boundary

> **Evidence boundary** — Reviewed:
- The CLI command surface and its fixed product vocabulary.
- The local .operator/ ledger layout and first-run bootstrap behavior.
- Task-bound writes that use the current task when one is not passed explicitly.
- Claim creation as an unverified task-linked record.
- Brief, handoff, session, and provenance behavior as the continuity layer around the core workflow.

Not reviewed:
- A live runtime .operator/ snapshot from an actual working workspace.
- External session logs used by usage import.
- Owner interview answers that would confirm the broader operating boundary.
- Any workflow beyond the bounded local tool that the repository evidence does not prove.

Recheck the manual against a fresh workspace by exercising the visible CLI entry points and comparing the resulting .operator/ layout and records with the described workflow. Confirm that first-run setup, repeat setup, task-bound writes, claim creation, brief and handoff generation, and session closeout still behave the same way. If live evidence shows a repair path, a broader system boundary, or different task-binding rules, revise the chapter boundary instead of stretching the current claims.

> Reviewed: blue-az/operator-control-plane repository snapshot, Founder/owner context

> Not reviewed: External runtime and integrations, Unreviewed runtime and owner context
