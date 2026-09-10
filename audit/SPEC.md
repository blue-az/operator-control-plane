# Record Seal — evidence-chain audit for run directories

**Family 3 (LSD third task family):** not PPR gold scoring, not Lane 2 intent,
not doc-claim liveness (family 2). This audits the **record itself** — the
manifest + evidence files a seat leaves behind — for internal consistency, so
that a reader can ground a claim on it later. It says nothing about whether
any model was good.

The failure it exists to catch: a run directory that *looks* complete but
whose manifest and evidence disagree (missing stdout, orphan evidence, a
returncode≠0 row secretly carrying a completion payload, repeated-row gaps,
mixed context, tag drift). Those are exactly the records a careless reader
quotes as if sealed.

## Where it lives

`operator-control-plane/audit/` — it belongs to the control plane (the
operator's ledger hygiene), not to any one domain. It has no dependency on
BT/Project Phoenix: it reads plain `manifest.json` + files.

## Contract (layered, fail-closed)

| code | applies when | meaning |
|------|-------------|---------|
| V-DUP | always | no two rows share (task, label) |
| V-OUT | always | every row `stdout_path` resolves (absolute or under `out_dir`) |
| V-ORPHAN | always | no `*_rN.out.md` on disk is unreferenced by any row |
| V-RC-ERR | always | a `returncode!=0` row must not have a payload with non-empty `raw_response` |
| V-REPEATS | manifest declares `repeats` | per (task, base_label) group: row count == repeats |
| V-CTX | any row has `num_ctx` | all rows share one `num_ctx` |
| V-TAG | manifest declares `model_configs` | row `request_model` == declared tag |

A recordless error — a 500 row with *no* payload file — is the **honest**
shape and must seal. (That is exactly how the qwen36-35b column looks, and
that is why this audit cannot be used to smear that column as a model
failure: it confirms the record is consistent with a transport failure.)

Unknown shapes (no `results`, rows not objects) are construction errors, not
skips — exit 12.

## Run

```bash
cd ~/operator-control-plane/audit
python3 -m unittest test_record_seal -v        # 11 tests, synthetic + live
python3 record_seal.py ../evals/ppr_agent_benchmark/runs/pinned-20260908-200455
```

Exit: 0 sealed · 11 violations · 12 construction. `--json` for machines.

## Cited findings (this checkout, 2026-09-10)

- `pinned-20260908-200455` — **sealed** (`rows=36`, all checks active incl.
  V-RC-ERR, V-CTX single=16384). The qwen36-35b 500 column is record-consistent.
- `20260907-grok-sweep` — **VIOLATION V-OUT**: three rows reference
  `ppr1_product_boundary__grok.out.md`, `ppr2_gate_query_semantics__grok.out.md`,
  and `ppr3_real_data_report__grok.out.md`, none present on disk. The record is
  not sealable as-is. Genuine ledger finding, not a test fixture.

## Claims we will not make

- No model-capability claim from any sealed/violated directory — seal status
  is about the record, not the seat.
- No "the Grok sweep failed" claim beyond the specific V-OUT violation and
  the missing filenames. (Grok is not a local seat; this is a record-gap.)
- No n≥1 generalization that "all runs seal clean" — the grok-sweep
  three-violation counterexample is part of the evidence the auditor is working.
