---
id: poe-fut014-invalid-provenance-confidence
title: POE-FUT-014 Invalid Provenance Confidence
status: draft
updated: 2026-09-05
---

# POE-FUT-014 Invalid Provenance Confidence

Operator files have used `confidence: measured`. Upstream allows only
`verified`, `inferred`, or `assumed` and fails closed (E011).

```pbc:actors
- id: operator_user
  name: Operator user
  type: human
  description: Records evidence.
```

```pbc:behavior
id: POE-FUT014-BHV-PROV
name: Attach provenance
actor: operator_user
description: A behavior with non-standard provenance confidence.
trust: provisional
```

```pbc:outcomes
- Provenance confidence is checked.
```

```pbc:provenance
- kind: runtime
  ref: tests/fixtures/poe_fut014/poe_fut014_invalid_provenance_confidence.pbc.md
  detail: Local measurement label used in Operator contracts.
  confidence: measured
```
