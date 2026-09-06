---
id: poe-fut014-invalid-proposed-plus-unknown
title: POE-FUT-014 Proposed Lifecycle Plus Unknown Block
status: draft
updated: 2026-09-05
---

# POE-FUT-014 Proposed Lifecycle Plus Unknown Block

YAML-valid `proposed-*` fences plus an unknown non-lifecycle type.
The wrapper may allowlist the proposed fences and must still emit E004
for `pbc:not-a-block`.

```pbc:actors
- id: operator_user
  name: Operator user
  type: human
  description: Owns proposal lifecycle rulings.
```

```pbc:proposed-rules
- id: POE-FUT014-RUL-MIXED
  name: Proposed lifecycle fence
  rule: Proposed material stays in pbc:proposed-rules.
  trust: proposed
```

```pbc:proposed-behavior
id: POE-FUT014-BHV-MIXED
name: Author a proposed behavior
actor: operator_user
description: YAML-valid proposed behavior.
trust: proposed
```

```pbc:proposed-outcomes
- Proposed fences remain distinct from pbc:rules.
```

```pbc:not-a-block
foo: bar
```
