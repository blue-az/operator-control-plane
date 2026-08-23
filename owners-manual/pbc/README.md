# Owner's Manual for blue-az/operator-control-plane — Agent-Ready Behavior Contracts

This directory contains draft Product Behavior Contract (PBC) projections generated from the unlocked Owner's Manual.

Use these files as structured context for coding agents, QA review, drift checks, and future product-contract work. They are intentionally separate from the human-readable manual because the manual explains the product; PBC files summarize behavior-contract candidates.

## Files

- `product-overview.pbc.md` — package-level draft contract context.
- `NN-chapter-name.pbc.md` — chapter-level draft behavior-contract projections.
- `appendix-opr-governed-llm-client.pbc.md` — draft target contract for extracting `opr`
  into this repository as a governed LLM client.
- `appendix-prime-agent-evidence-ingestion.pbc.md` — draft target contract for ingesting Prime
  Agent session records as usage and as claim evidence. Ledger task: `pa-evidence`. Gate 0 is
  unmet: no Prime Agent session has been observed on this machine.
- `appendix-local-routing-corpus.pbc.md` — draft target contract for harvesting real tasks from
  this machine's harness logs and establishing by execution which could route locally. Ledger
  task: `local-routing-corpus`. Gated on a fixturability probe that has not been run.
- `appendix-multi-session-coordination.pbc.md` — draft working agreement for concurrent agent
  sessions sharing one ledger. Ledger task: `session-coordination-protocol`. Both Claude sessions
  have signed off; awaiting an operator ruling on the identity labels.
- `appendix-local-implementer-dispatch.pbc.md` — draft contract for dispatching a local-model
  seat from a ledger brief (`opr --task`) instead of pasted recaps. Ledger task:
  `proposal-lifecycle`. Proposed only; not implemented.

## Trust Model

- Status is `draft` unless a human owner reviews and accepts the contract.
- Uncertainty from the manual remains uncertainty here.
- Missing repositories or external systems should stay visible as grounding context, not be converted into invented behavior.

Source: blue-az/operator-control-plane:main@9b9e3e63a7f0f54ccde541c6c10570c8fdbe8f5b
