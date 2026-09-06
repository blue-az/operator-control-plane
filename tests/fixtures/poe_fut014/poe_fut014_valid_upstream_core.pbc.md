---
id: poe-fut014-valid-upstream-core
title: POE-FUT-014 Valid Upstream Core
status: draft
updated: 2026-09-05
---

# POE-FUT-014 Valid Upstream Core

Portable subset using only upstream-known blocks and trust values.
This fixture should pass stock `pbc validate` and `pbc_lint.py`.

```pbc:actors
- id: operator_user
  name: Operator user
  type: human
  description: Owns the compatibility decision.
```

```pbc:behavior
id: POE-FUT014-BHV-CORE
name: Validate a portable PBC
actor: operator_user
description: A behavior that uses only upstream-stable fields.
trust: provisional
```

```pbc:outcomes
- Stock pbc validate exits 0.
```

```pbc:rules
- id: POE-FUT014-RUL-CORE
  name: Portable rule
  rule: Use only known block types and trusted/provisional/scaffolding trust values.
  trust: provisional
```
