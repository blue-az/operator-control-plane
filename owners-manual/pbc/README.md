# Owner's Manual for blue-az/operator-control-plane — Agent-Ready Behavior Contracts

This directory contains draft Product Behavior Contract (PBC) projections generated from the unlocked Owner's Manual.

Use these files as structured context for coding agents, QA review, drift checks, and future product-contract work. They are intentionally separate from the human-readable manual because the manual explains the product; PBC files summarize behavior-contract candidates.

## Files

- `product-overview.pbc.md` — package-level draft contract context.
- `NN-chapter-name.pbc.md` — chapter-level draft behavior-contract projections.
- `appendix-opr-governed-llm-client.pbc.md` — **deprecated.** Historical contract for
  the old `opr` governed REPL. Do not implement continuation. Restore from git
  (`fe4211b`) if needed.
- `appendix-prime-agent-evidence-ingestion.pbc.md` — draft target contract for ingesting Prime
  Agent session records as usage and as claim evidence. Ledger task: `pa-evidence`. Gate 0 is
  unmet: no Prime Agent session has been observed on this machine.
- `appendix-local-routing-corpus.pbc.md` — draft target contract for harvesting real tasks from
  this machine's harness logs and establishing by execution which could route locally. Ledger
  task: `local-routing-corpus`. Gated on a fixturability probe that has not been run.
- `appendix-multi-session-coordination.pbc.md` — draft working agreement for concurrent agent
  sessions sharing one ledger. Ledger task: `session-coordination-protocol`. Both Claude sessions
  have signed off; awaiting an operator ruling on the identity labels.
- `appendix-local-implementer-dispatch.pbc.md` — dispatch contract, ratified 2026-08-23 against
  an OpenCode carrier. Ledger task: `proposal-lifecycle`. LID-RUL-101–105 are provisional and
  LID-BHV-001 remains proposed; all of them need re-ratification against the `pi` carrier
  (superseded 2026-08-28) before they bind.
- `appendix-pi-operator-extension.pbc.md` — draft contract for a project-local Pi extension
  wrapping the Operator CLI. Ledger task: `pi-operator-extension-pbc-review`. POE-RUL-101–113
  are proposed and unratified; verified block POE-RUL-001–005 records the CLI constraints they
  must respect.

## Trust Model

- Status is `draft` unless a human owner reviews and accepts the contract.
- Uncertainty from the manual remains uncertainty here.
- Missing repositories or external systems should stay visible as grounding context, not be converted into invented behavior.

Source: blue-az/operator-control-plane:main@9b9e3e63a7f0f54ccde541c6c10570c8fdbe8f5b
