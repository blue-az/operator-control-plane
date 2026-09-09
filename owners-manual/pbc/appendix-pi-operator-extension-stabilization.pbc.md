---
id: pi-operator-extension-stabilization
title: Pi Operator extension stabilization and carrier-neutral surface
status: draft
updated: 2026-09-08
---

# Pi Operator extension stabilization

## Product shape

Freeze a small, working Pi Operator extension contract before adding new carriers
or expanding the command surface. Separate stable Operator integration from
experimental Pi/Surface behavior, and make the integration reusable by a future
Stella plugin adapter.

```pbc:actors
- id: owner
  name: Owner
  type: human
  description: Approves ledger mutations and contract changes.
- id: pi
  name: Pi runtime
  type: system
  description: Loads project-local commands and renders reports.
- id: operator
  name: Operator ledger
  type: system
  description: Remains the authority for tasks, claims, evidence, identity, and verification.
- id: carrier
  name: Future carrier adapter
  type: system
  description: Translates a carrier lifecycle into the stable integration surface.
```

## Stable v1 scope

- read-only `/op:doctor`, `/op:status`, `/op:tasks`, `/op:next-steps`, `/op:project`, and `/op:roadmap`;
- confirmed `/op:use` and basic task/session selection;
- session start/end and usage receipts;
- brief and handoff generation;
- a carrier-neutral Operator client with fixed argv construction, explicit task scope, idempotent writes, and fail-closed errors;
- discovery of a configured external ledger from another project cwd without copying or silently overriding ledger state.

## Experimental scope

Keep these out of the stable contract until separately accepted:

- `/op:claim`, `/op:evidence`, `/op:delegate`, and `/op:supervisor-review` expansions;
- `/pbc:define`, `/pbc:feature`, and PBC lifecycle wizards;
- fleet integration and automated verification;
- Stella wrapper/plugin transport;
- model-callable mutation tools.

## Load-bearing rules

1. Operator remains the authority; adapters must not duplicate ledger semantics.
2. No adapter may mark a claim verified or accept `--status`, `--verified-by`, or `--verdict` as free inputs.
3. Mutating actions require explicit owner confirmation and preserve Operator identity checks.
4. Every task-scoped operation names its task explicitly; session selection is not ledger state.
5. Missing or malformed external-ledger configuration fails closed.
6. Carrier adapters translate lifecycle and presentation only; they do not weaken producer/verifier separation.
7. Stable behavior is tested from a consumer cwd, not only from the Operator source tree.

## Acceptance outcomes

```pbc:proposed-outcomes
- A stable v1 command inventory and compatibility policy are documented.
- The shared Operator client can be exercised without importing Pi UI modules.
- A consumer project can discover the configured ledger and load the extension without copying `.operator/` data.
- Existing Pi commands retain their safety allowlist and identity/provenance rules.
- Session and usage receipt operations are idempotent under repeated lifecycle events.
- Experimental commands are visibly labeled and cannot silently expand the v1 contract.
- A Stella adapter can consume the stable client through a separate transport layer without duplicating ledger logic.
- Pi and consumer-cwd selftests pass, and failures from missing ledger/configuration are explicit.
```

## Non-goals

This contract does not implement `/pbc:*`, port the extension to Stella, change
Operator verification semantics, or make Stella's self-reported plugin oracle
an independent verifier. Those require separate feature contracts and review.
