---
id: poe-fut014-invalid-unknown-confidence
title: POE-FUT-014 Unknown Provenance Confidence
status: draft
updated: 2026-09-05
---

# POE-FUT-014 Unknown Provenance Confidence

`confidence: established` is not an upstream value and is not the
Operator-local `measured` vocabulary. The wrapper must keep E011.
Do not relabel this as verified.

```pbc:actors
- id: operator_user
  name: Operator user
  type: human
  description: Records evidence.
```

```pbc:behavior
id: POE-FUT014-BHV-CONF-UNKNOWN
name: Attach provenance
actor: operator_user
description: A behavior with an unsupported provenance confidence.
trust: provisional
```

```pbc:outcomes
- Unsupported confidence remains an error.
```

```pbc:provenance
- kind: runtime
  ref: tests/fixtures/poe_fut014/poe_fut014_invalid_unknown_confidence.pbc.md
  detail: Invented confidence label that must not be treated as established.
  confidence: established
```
