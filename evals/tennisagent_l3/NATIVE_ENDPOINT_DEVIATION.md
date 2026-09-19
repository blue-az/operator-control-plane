# Native Ollama endpoint deviation

Status: quarantined; re-run required.

The first native TennisAgent L3 canaries and extended pilots used the default
Ollama API endpoint (`127.0.0.1:11434`). During the extended run, `nvidia-smi`
showed one llama-server PID with memory resident on both RTX 3090 devices.
That is model spreading, not canonical single-card placement.

Affected artifacts:

- `NATIVE_PILOT_RESULT.json` (18-cell pilot)
- `NATIVE_EXTENDED_RESULT.json` (18-cell extended pilot)
- prior native canary outputs and iteration rows produced through the default
  endpoint
- the interrupted partial extended run

Disposition: do not use these results as single-3090 evidence. They remain
useful harness-development evidence only. The original L2 reference runs are
unaffected because they used the pinned placement path.

Required re-run gate:

1. start or identify the pinned single-card Ollama daemon;
2. route `/api/chat` to that explicit endpoint;
3. verify model residency on exactly one GPU before the first cell;
4. enforce the per-cell host gate and placement telemetry;
5. attach the new traces separately from the quarantined artifacts.

Follow-up: the first attempted custom endpoint still did not produce a
model-residency event on the CUDA-only daemon; the observed response was not
accepted as proof of single-card placement. The adapter must record the exact
endpoint and require an `/api/ps`/`nvidia-smi` observation tied to the active
request before accepting a cell.
