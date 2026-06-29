# Owner's Manual for blue-az/operator-control-plane — Agent-Ready Behavior Contracts

This directory contains draft Product Behavior Contract (PBC) projections generated from the unlocked Owner's Manual.

Use these files as structured context for coding agents, QA review, drift checks, and future product-contract work. They are intentionally separate from the human-readable manual because the manual explains the product; PBC files summarize behavior-contract candidates.

## Files

- `product-overview.pbc.md` — package-level draft contract context.
- `NN-chapter-name.pbc.md` — chapter-level draft behavior-contract projections.
- `07-opr-governed-llm-client.pbc.md` — draft target contract for extracting `opr`
  into this repository as a governed LLM client.

## Trust Model

- Status is `draft` unless a human owner reviews and accepts the contract.
- Uncertainty from the manual remains uncertainty here.
- Missing repositories or external systems should stay visible as grounding context, not be converted into invented behavior.

Source: blue-az/operator-control-plane:main@9b9e3e63a7f0f54ccde541c6c10570c8fdbe8f5b
