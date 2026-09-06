---
id: poe-fut014-invalid-rules-trust-proposed
title: POE-FUT-014 Rules Carrying Trust Proposed
status: draft
updated: 2026-09-05
---

# POE-FUT-014 Rules Carrying Trust Proposed

Operator invariant 1: a ratified `pbc:rules` fence must not carry
`trust: proposed`. Upstream treats `proposed` as an invalid trust
warning (W013), not an error.

```pbc:rules
- id: POE-FUT014-RUL-HALF-RATIFIED
  name: Half-finished ratification
  rule: This combination is the half-finished ratification case.
  trust: proposed
```
