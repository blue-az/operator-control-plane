---
id: poe-fut014-valid-local-trust
title: POE-FUT-014 Valid Local Trust Values
status: draft
updated: 2026-09-05
---

# POE-FUT-014 Valid Local Trust Values

Known upstream block types carrying Operator-local trust vocabulary
(`verified`, `proposed`) on `pbc:behavior`. `pbc:rules` uses `verified`
only (not `proposed`) so Operator invariant 1 is not triggered.

```pbc:actors
- id: operator_user
  name: Operator user
  type: human
  description: Records local trust labels.
```

```pbc:behavior
id: POE-FUT014-BHV-TRUST
name: Record local trust
actor: operator_user
description: Operator uses trust values beyond the upstream enum.
trust: verified
```

```pbc:outcomes
- Local trust values are visible to tooling.
```

```pbc:rules
- id: POE-FUT014-RUL-TRUST
  name: Local verified rule
  rule: Operator records some live CLI facts as trust verified.
  trust: verified
```
