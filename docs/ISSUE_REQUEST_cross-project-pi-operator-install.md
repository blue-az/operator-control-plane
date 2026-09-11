# Issue request: cross-project Pi Operator installation

**Promoted from:** `POE-FUT-012`  
**Status:** issue candidate  
**Repository:** `operator-control-plane`

## Problem

The Operator Pi extension is checked into this repository at
`.pi/extensions/operator/`, but `/op:*` only appears when Pi is running in a
project that has the extension installed and can discover the corresponding
Operator ledger. This makes the extension look like an Operator-folder-only
feature and encourages copy/paste installation.

## Requested outcome

Provide a supported cross-project installation path that:

- installs, copies, or links the extension into a target project without
  hand-copying files;
- discovers/configures the standalone Operator ledger through the existing
  `.pi/operator-ledger.json` contract;
- keeps Operator independent of Project Phoenix;
- clearly reports when the extension is installed but no valid ledger contract
  exists;
- includes starter guidance for a target project's agents;
- defines source-vs-installed paths so the Magic dashboard can link the
  canonical source accurately.

## Acceptance criteria

1. A disposable target project can install the extension with one documented
   command.
2. `/op:status` and `/op:roadmap` work from that target project against the
   configured Operator ledger.
3. A missing or malformed ledger contract fails clearly and does not guess a
   ledger root.
4. The install path does not copy `.operator/` data into the target project.
5. Tests cover copy/link installation, contract discovery, and failure cases.
6. The README and install guide document upgrade/removal and source provenance.

## Source contract

- `owners-manual/pbc/appendix-pi-operator-extension.pbc.md` — `POE-FUT-012`
- `.pi/extensions/operator/install-guide.md`
- `.pi/extensions/operator/README.md`
- `scripts/install-operator-extension.py`
