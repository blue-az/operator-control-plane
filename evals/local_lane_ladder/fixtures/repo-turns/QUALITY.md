# repo-turns quality — A / B / C

Same instrument as the z13 characterization pack
(`machines/z13-amd/ollama/characterization/RESULTS.md`): one programmatic
grader, three writers, no LLM judge.

| | writer | here | z13 (29 tasks) |
|---|---|---|---|
| **A** | `gemma4:31b` n=1 | mean of n=3 @ T=0.8 | **0.96** greedy |
| **B** | `gemma4:26b` n=1 | mean of n=3 @ T=0.8 | 0.93 greedy |
| **C** | `gemma4:26b` best-of-N | best of n=3 | 0.95 best-of-5 |

Checks per cell (each 0/1, score = mean): `required` (postcondition),
`scoped` (writes only the declared file), `clean_write` (no failed patch).

| task | A 31b mean | B 26b mean | C 26b best-of-3 |
|---|---:|---:|---:|
| `bothread-lease-ttl` | 1.00 | 1.00 | 1.00 |
| `code-stick-github-url` | 0.67 | 1.00 | 1.00 |
| `groundtruth-web-port` | 1.00 | 1.00 | 1.00 |
| `ollm-utf8-sig` | 0.89 | 1.00 | 1.00 |
| `projectkitty-snippet-lines` | 1.00 | 1.00 | 1.00 |
| **overall** | **0.91** | **1.00** | **1.00** |

## Where they separate

- `code-stick-github-url` `gemma4:31b`: t1 0.67 {'scoped'}; t2 0.67 {'scoped'}; t3 0.67 {'scoped'}
- `ollm-utf8-sig` `gemma4:31b`: t3 0.67 {'clean_write'}

## Read against z13

On z13, 31b won because **codegen** and **longctx** did not saturate.
This pack's `required` check saturates (30/30 pass). Quality here is
scope and clean writes. 31b loses `code-stick` (`package.json` extra)
and one `ollm` retry. That is FILE / TOOL, not the z13 win.

Do not pool this overall with z13 0.96. Different tasks.
