---
id: poe-fut014-invalid-malformed-proposed-yaml
title: POE-FUT-014 Malformed Proposed-Rules YAML
status: draft
updated: 2026-09-05
---

# POE-FUT-014 Malformed Proposed-Rules YAML

YAML-invalid body inside an Operator lifecycle fence. Route C must still
fail closed with E005. Allowlisting `proposed-rules` does not suppress
parse errors.

```pbc:actors
- id: operator_user
  name: Operator user
  type: human
  description: Owns proposal lifecycle rulings.
```

```pbc:proposed-rules
- id: POE-FUT014-RUL-BAD-YAML
  name: Broken proposed rule
  rule: this fence is proposed
  trust: proposed
  bad_indent:
 broken: true
```
