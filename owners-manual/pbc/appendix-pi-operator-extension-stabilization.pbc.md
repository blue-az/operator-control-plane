---
id: pi-operator-extension-stabilization
title: Pi Operator extension stabilization and carrier-neutral surface
status: draft
updated: 2026-09-09
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

The draft is reconciled against the current implementation below. The extension
is project-local (Pi does not discover it by walking parent directories), while
ledger discovery is deliberately cross-project through `.pi/operator-ledger.json`.

- read-only `/op:doctor`, `/op:status`, `/op:tasks`, `/op:next-steps`, `/op:project`, and `/op:roadmap`;
- confirmed `/op:use` (session-local selection; ledger `current_task` only after confirmation) and basic task/session selection;
- session start/end and usage receipts;
- brief and handoff generation;
- a carrier-neutral Operator client with fixed argv construction, explicit task scope, idempotent writes, and fail-closed errors;
- discovery of a configured external ledger from another project cwd without copying or silently overriding ledger state.

### Implementation reconciliation (2026-09-09)

| Contract item | Current state | Compatibility decision |
|---|---|---|
| Consumer extension discovery | Installer copies/links `.pi/extensions/operator`; Pi loader requires the consumer cwd and project trust | Supported; nested cwd discovery is not implied |
| External ledger discovery | `core.ts` `findLedger` validates the v1 contract, absolute root, sibling `.operator/` + `operator` pair, and ambiguity | Supported and fail-closed |
| Carrier-neutral client | `.pi/extensions/operator/client.ts` exports `OperatorClient` / `CarrierNeutralOperatorClient`; it imports no Pi UI modules and delegates only fixed argv builders | Stable v1 surface |
| Session lifecycle | Safe `session-start` and `session-end` builders/client methods exist; repeated already-running/already-closed transitions are idempotent results | Supported without status transitions |
| Usage receipts | Created/closed by Operator session lifecycle; no direct arbitrary `usage-add` passthrough | Supported through lifecycle only |
| `/op:use` | Session selection is display state; `task-use` writes ledger `current_task` only after confirmation | Supported |
| Consumer-cwd load | Pi `discoverAndLoadExtensions` is cwd-local; nested default discovery is empty; explicit `loadExtensions(index.ts)` works; DefaultResourceLoader trust-gates the project extension | Supported; covered by consumer-cwd tests |
| PBC and Stella transport | No `/pbc:*` wizard and no Stella adapter | Deferred, separate contracts |

The client is intentionally a transport seam, not a second ledger implementation:
carriers provide an `exec` function and receive Operator command results.

## Experimental scope

Keep these out of the stable contract until separately accepted:

- `/op:claim`, `/op:evidence`, `/op:delegate`, `/op:supervisor-review`, and `/op:popup` expansions;
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
