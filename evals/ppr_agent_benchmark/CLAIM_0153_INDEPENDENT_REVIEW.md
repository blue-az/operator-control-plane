# claim-0153: independent inspection, quarantine unchanged

Author: Codex via pi, Unix UID 1000 (same UID as builder; advisory only).
Scope: runner maintenance and bounded read-only evidence review, not a model benchmark campaign.
Stop criteria: offline runner regressions, individual historical checker runs, existing gold tests, evidence/input integrity checks. No model calls, ledger mutations, score rewrites, or ppr-agent edits.

## Evidence inspected

Read claim-0153, both review delegation YAML bundles (2026-09-03 and 2026-09-06), the quarantine reason, and all five referenced evidence records and payloads under `.operator/evidence/ppr-benchmark-gold-standard-checker/`.

- All five payload SHA-256 hashes match their evidence metadata.
- Live DB, PBC, and published-subset hashes match the gold manifest; ppr-agent HEAD matches `04ed8ed9ce8095cbeedc09d5aa218e7ffb2565ad`.
- Independently invoked `python3 -m unittest test_gold_standard -v`: five tests pass, including live Lane B and rejection of reasoning-only content.
- Individually invoked `python3 check_run.py runs/<run>` without `--write`: `20260825-192929` exits 0, `20260826-204923` exits 0, `20260826-204632` exits 2.
- These establish present reproducibility of the tested paths, not historical proof of every assertion (such as no model calls or no edits at authoring time).

## Review command is not fail-closed

The current claim and September 6 bundle use:

```sh
python3 -m unittest test_gold_standard 2>&1 | tail -2 && python3 check_run.py runs/20260825-192929 >/dev/null 2>&1 && python3 check_run.py runs/20260826-204632 >/dev/null 2>&1; test $? -eq 2 && python3 -m py_compile check_run.py test_gold_standard.py && echo VERIFY_OK
```

1. Without pipefail, `tail` hides a failing unittest exit.
2. The final `test $? -eq 2` can accept failure of the positive-control run, without ever running the intended negative control.
3. It omits positive control `20260826-204923`, present in the September 3 bundle.

Executed safe shell-control-flow probes independently; both incorrectly exit 0 and print `VERIFY_OK`:

```sh
false | tail -2 && true && (exit 2); test $? -eq 2 && echo VERIFY_OK
true | tail -2 && (exit 2) && true; test $? -eq 2 && echo VERIFY_OK
```

A future distinct-UID review should run each stage explicitly, or use this bounded structure from the benchmark directory (compile to verifier-owned scratch if necessary):

```sh
python3 -m unittest test_gold_standard -v &&
python3 check_run.py runs/20260825-192929 &&
python3 check_run.py runs/20260826-204923 &&
( python3 check_run.py runs/20260826-204632; rc=$?; test "$rc" -eq 2 ) &&
PYTHONPYCACHEPREFIX="$(mktemp -d)" python3 -m py_compile check_run.py test_gold_standard.py
```

## Disposition

Quarantine remains appropriate and unchanged. Original verification was withdrawn because evidence-0001 through 0003 had no `verification_command`; evidence-0005 now carries one but is explicitly builder-produced, UID 1000, not independent verification. Its command also has the failure-masking problems above. The September 6 delegation describes intended UID-isolated review; it is not proof that review completed.

Do not backfill old evidence or promote this advisory note into UID-isolated acceptance. A distinct authorized verifier needs new attributable evidence with a fail-closed command. Runner repairs do not resolve this claim.
