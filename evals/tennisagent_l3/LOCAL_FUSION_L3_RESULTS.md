# TennisAgent Fusion L3 — local native pilot

Status: preliminary local result; not a cross-provider ranking.

Protocol:

- native Ollama tool calls;
- explicit CUDA-only single-3090 daemon on testbench;
- swap-free host state;
- three local models;
- six task classes, n=3 each;
- 54 unique cells (six task classes × three models × n=3); targeted edge reruns are retained separately and not double-counted.

## Reconciled outcome

| Model | Passes | Cells | Mean wall-clock |
|---|---:|---:|---:|
| qwen3.6:35b | 18/18 | 18 | 9.7 s |
| qwen3.8:27b | 18/18 | 18 | 16.2 s |
| gemma4:26b | 18/18 | 18 | 9.4 s |

Task classes:

```text
valid linked evidence
invalid-date preservation
weather provenance
two-session comparison
missing synchronized data
unmatched/unpaired records
```

All models completed the native chains and preserved the tested invalid/missing
states. The quality battery is therefore saturated at this pilot difficulty;
wall-clock differences are descriptive only until a harder task design is
introduced.

The default-Ollama native artifacts are quarantined separately in
`NATIVE_ENDPOINT_DEVIATION.md`. This packet uses only the explicit CUDA-only
endpoint traces and reconciled semantic graders.
