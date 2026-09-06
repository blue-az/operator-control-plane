---
id: poe-fut014-invalid-missing-confidence
title: POE-FUT-014 Missing Provenance Confidence
status: draft
updated: 2026-09-05
---

# POE-FUT-014 Missing Provenance Confidence

Provenance without `confidence`. Allowlisting `measured` must not
blanket-ignore E011.

```pbc:actors
- id: operator_user
  name: Operator user
  type: human
  description: Records evidence.
```

```pbc:behavior
id: POE-FUT014-BHV-CONF-MISSING
name: Attach provenance
actor: operator_user
description: A behavior whose provenance omits confidence.
trust: provisional
```

```pbc:outcomes
- Missing confidence remains an error.
```

```pbc:provenance
- kind: runtime
  ref: tests/fixtures/poe_fut014/poe_fut014_invalid_missing_confidence.pbc.md
  detail: Confidence field omitted on purpose.
```
