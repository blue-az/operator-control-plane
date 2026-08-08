# Local Lane Ladder — Results

Generated from 216 trial records.

> **These measure model + pre-`890d595` harness, not model ability.**
> Relabeled 2026-08-08 per the codex audit
> (`.operator/evidence/opr-continuation-loop-audit/evidence-0008.md`).
>
> Every trial ran through `opr` when `run_command` was a *terminal* tool: the agent loop
> returned on its first successful state-changing command. A model that spent a command on
> discovery or verification before the required mutation was recorded as a failure whether or
> not it was capable. Per-trial traces were not retained, so the two cannot be separated now.
>
> - The **128 passing trials remain valid.** A deterministic postcondition that was met was
>   met; harness truncation cannot fabricate a real file or output state.
> - The **88 failing trials are confounded** and must not be read as model-capability findings
>   until rerun with traces preserved.
> - The pass-rate arithmetic below is correctly computed from the records. What is affected is
>   its *interpretation* as relative model ability, since removing false negatives moves cells.
>
> The 120s read timeout fixed in `d5eea34` is **not** implicated here: the slowest failing
> trial finished in 72.1s, well inside that limit.

## Pass rate per model x level (all tasks combined)

| Model | L0 | L1 | L2 |
|---|---|---|---|
| gemma4:26b | 9/18 | 12/18 | 18/18 |
| gemma4:31b | 15/18 | 16/18 | 17/18 |
| llama3.1:8b | 0/18 | 7/18 | 5/18 |
| qwen2.5-coder:32b | 0/18 | 12/18 | 17/18 |

## Per-task breakdown

### alias-add

| Model | L0 | L1 | L2 |
|---|---|---|---|
| gemma4:26b | 1/3 | 2/3 | 3/3 |
| gemma4:31b | 3/3 | 1/3 | 3/3 |
| llama3.1:8b | 0/3 | 0/3 | 0/3 |
| qwen2.5-coder:32b | 0/3 | 3/3 | 3/3 |

### config-value-change

| Model | L0 | L1 | L2 |
|---|---|---|---|
| gemma4:26b | 1/3 | 3/3 | 3/3 |
| gemma4:31b | 3/3 | 3/3 | 3/3 |
| llama3.1:8b | 0/3 | 2/3 | 2/3 |
| qwen2.5-coder:32b | 0/3 | 3/3 | 3/3 |

### doc-fix

| Model | L0 | L1 | L2 |
|---|---|---|---|
| gemma4:26b | 0/3 | 3/3 | 3/3 |
| gemma4:31b | 0/3 | 3/3 | 3/3 |
| llama3.1:8b | 0/3 | 0/3 | 0/3 |
| qwen2.5-coder:32b | 0/3 | 0/3 | 3/3 |

### function-add

| Model | L0 | L1 | L2 |
|---|---|---|---|
| gemma4:26b | 3/3 | 1/3 | 3/3 |
| gemma4:31b | 3/3 | 3/3 | 2/3 |
| llama3.1:8b | 0/3 | 2/3 | 1/3 |
| qwen2.5-coder:32b | 0/3 | 0/3 | 2/3 |

### grep-and-report

| Model | L0 | L1 | L2 |
|---|---|---|---|
| gemma4:26b | 3/3 | 3/3 | 3/3 |
| gemma4:31b | 3/3 | 3/3 | 3/3 |
| llama3.1:8b | 0/3 | 3/3 | 2/3 |
| qwen2.5-coder:32b | 0/3 | 3/3 | 3/3 |

### multi-file-rename-reference

| Model | L0 | L1 | L2 |
|---|---|---|---|
| gemma4:26b | 1/3 | 0/3 | 3/3 |
| gemma4:31b | 3/3 | 3/3 | 3/3 |
| llama3.1:8b | 0/3 | 0/3 | 0/3 |
| qwen2.5-coder:32b | 0/3 | 3/3 | 3/3 |
