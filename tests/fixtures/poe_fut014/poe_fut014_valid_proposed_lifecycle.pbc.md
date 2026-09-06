---
id: poe-fut014-valid-proposed-lifecycle
title: POE-FUT-014 Valid Proposed Lifecycle
status: draft
updated: 2026-09-05
---

# POE-FUT-014 Valid Proposed Lifecycle

YAML-valid Operator dialect using `pbc:proposed-*` fences and `trust: proposed`.
This is a proposed block, not a ratified rule. The audit must not treat
recognition of these fences as ratification.

```pbc:actors
- id: operator_user
  name: Operator user
  type: human
  description: Owns proposal lifecycle rulings.
```

```pbc:proposed-rules
- id: POE-FUT014-RUL-PROPOSED
  name: Proposed lifecycle fence
  rule: >
    Operator keeps proposed material in pbc:proposed-rules rather than
    pbc:rules until an operator ruling and a distinct ratifier move it.
  trust: proposed
```

```pbc:proposed-behavior
id: POE-FUT014-BHV-PROPOSED
name: Author a proposed behavior
actor: operator_user
description: >
  A YAML-valid proposed behavior using the Operator lifecycle fence.
trust: proposed
```

```pbc:proposed-outcomes
- Proposed fences remain distinct from pbc:rules.
- Invalid YAML is still rejected by a compatibility profile.
- Unsupported unknown blocks are not silently dropped.
```
