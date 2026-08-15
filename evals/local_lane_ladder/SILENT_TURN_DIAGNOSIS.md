# The silent turn: diagnosed as a server-side stall in ollama 0.32.12

**Investigated:** 2026-08-15, from two clean traces (`strict-table-render`,
`qwen3.8:27b`, trials 17 and 18) plus the ollama service journal.
**Not UID-verified. No claim registered.**

Two prior attempts failed to explain this — gemma4:31b going silent on the
Hyperlambda probe (2026-08-14, two theories tested and refuted). This is the
first time it was caught with server logs attached.

## The finding

**The hang is server-side, and the model is never invoked.**

ollama accepted the request at 03:42:27 and logged **nothing at all** for the
next ten minutes: no `slot get_availabl`, no `launch_slot_`, no `init_sampler`,
no `print_timing`. A healthy request emits all of those within milliseconds.
The request was finally closed at 03:52:26 by the *client* —

```
level=INFO source=llama_server.go:1536
  msg="aborting completion request due to client closing the connection"
[GIN] 03:52:26 | 500 | 9m59s | POST "/api/generate"
```

— which is the eval runner's own 600s timeout firing, three seconds later. The
HTTP 500 is therefore an **effect of the timeout, not its cause**.

Activity per minute across the window makes it unambiguous:

```
03:42  238 entries     <- previous cell finishing, then t17 accepted
03:43  (nothing)
  ...   nine minutes of complete silence
03:51  (nothing)
03:52    2 entries     <- client closes, 500 logged
```

**Consequence: the two timeout cells must not be charged to `qwen3.8:27b`.**
No tokens were generated and no slot was ever launched, so nothing about the
model's capability was measured. `FINDING.md` for that pack scores them as
`TIMEOUT`, not `MODEL_FAILURE`, and that is correct.

## A second, distinct ollama bug in the same window

Six seconds before the first stall, ollama failed to parse a tool call the model
emitted:

```
WARN source=qwen3coder.go:71  msg="qwen tool call parsing failed" error=EOF
WARN source=qwen35.go:108     msg="qwen3.5 tool call parsing failed" error=EOF
[GIN] 03:42:21 | 500 | 3.99s | POST "/api/generate"
```

Both parsers hit `EOF` mid-tool-call and the request 500s. This has happened
**10 times since 2026-08-01** on this machine. It is server-side: the model
produced output, and ollama could not read it.

This matters for `qwen3.6:27b` as much as `qwen3.8:27b` — both report
`architecture qwen35`, so both go through `qwen35.go`.

## What is NOT established

**The parse failure does not explain the stall.** The tempting story — a failed
parse leaves the server wedged — is contradicted by the evidence:

| parse failure | what followed |
|---|---|
| 03:38:33 | ~25 successful requests over the next 90 seconds. Server healthy. |
| 03:42:21 | t17 accepted, ten minutes of silence, then two stalls back to back. |

Ten parse failures since 2026-08-01 produced two stalls. So a parse failure is
neither sufficient nor obviously causal. Both stalls today happened to follow
one, and eight other parse failures did not. That is a correlation worth
recording and not a mechanism.

The slot was also released normally before the stall (`slot release ... stop
processing`, `srv update_slots: all slots are idle`), so this is not a case of
the previous request holding the slot.

## The harness defect that hid this twice

`opr` contains **zero `flush=True` calls**, and the runner did not force
unbuffered output. With stdout on a pipe, Python block-buffers; when the runner
SIGKILLs a timed-out process, the buffer dies with it. Both hung cells recorded
**0 bytes of stdout** despite opr printing `Routing task to:` before it ever
contacts the model.

So the trace was diagnostically empty for exactly the cells that needed it, and
appeared to say "opr never started" when it says nothing at all. Fixed:
`runner.py` now passes `PYTHONUNBUFFERED=1` into the subprocess environment, so
partial output survives the kill and shows how far a turn actually got.

This is the reason the 2026-08-14 investigation went nowhere.

## Environment

`ollama version 0.32.12`, single RTX 3090 320W, `qwen3.8:27b` (arch `qwen35`,
27.3B, Q4_K_M). Both stalls are the only multi-minute 500s since 2026-08-01.

## Next steps

1. **Do not attribute silent turns to a model** without checking
   `journalctl -u ollama` for the window. Three models have now shown this shape
   (gemma4:31b, qwen3.8, and qwen3.6 during an `/init` per operator report), which
   is itself evidence against a model-specific cause.
2. **The `qwen35.go` EOF parse failure is reportable upstream** as its own bug,
   independent of the stall. 10 occurrences, reproducible enough to characterise.
3. Re-run the two lost cells once the pack matters; they are currently unscored.
4. If the stall recurs with `PYTHONUNBUFFERED=1` in place, the opr-side partial
   output will show whether the client ever got a response header — which is the
   piece this investigation still lacks.
