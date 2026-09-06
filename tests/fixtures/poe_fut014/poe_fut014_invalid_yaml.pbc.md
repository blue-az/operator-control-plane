---
id: poe-fut014-invalid-yaml
title: POE-FUT-014 Invalid YAML Block
status: draft
updated: 2026-09-05
---

# POE-FUT-014 Invalid YAML Block

Malformed YAML inside a known block. Upstream CLI must fail closed (E005).
Operator `pbc_lint.py` currently does not parse YAML.

```pbc:actors
- id: test_actor
  name: Test actor
  type: human
  description: A test actor.
  bad_indent:
 broken: true
```
