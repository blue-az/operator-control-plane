# deepseek-r1:70b — screening finding (not run through E9)

**Date:** 2026-08-29, desktop. Screened, not battery-tested, following the same
"characterize before committing GPU time" pattern used for `gpt-oss:120b`
(`gptoss-120b-e9/FINDING.md`). This model was pulled, characterized, and the
result is: park it. Model deleted after this record was written.

**Model:** `deepseek-r1:70b` -- the Llama-70B distillation of R1 (`family:
llama`, not DeepSeek's own native MoE architecture), 70.6B dense params, GQA
64:8, Q4_K_M, 42 GB on disk, native context 131072.

## 1. Context-length trap (dense model, not MoE)

Left unpinned, the model loads at its full native 131072 context. For a
**dense** 70B model the KV cache at that size is enormous: total resident
footprint hit ~67 GB (42.6 GB weights + ~24 GB KV cache alone), overflowing
the 48 GB combined dual-3090 pool and forcing heavy CPU spill. Decode
collapsed to **2.12 tok/s**. Pinned to `num_ctx=16384` (the harness standard),
the whole model fits GPU-resident (45.5 GB, zero CPU spill) and decode jumps
to **17.9 tok/s** -- confirmed twice, consistent across two independent
single-shot calls (2788 tok / 155.6s and 1729 tok / 96.1s). Still the
slowest decode of any model characterized this session.

## 2. Thinking cannot be turned off

`think:false` does not suppress generation of the `<think>...</think>` block
-- verified directly via the native `/api/generate` endpoint: with
`think:false` set, the raw `<think>` tag appears inline in `response` instead
of being parsed into a separate `thinking` field. The model always spends a
real, often long, thinking phase before any visible output, regardless of
client-side settings.

## 3. Tool use is broken by a template defect, not a `pi`/dispatch problem

Initial symptom: a `pi`-driven E9 trial produced zero tool calls and a
hallucinated success narrative (fabricated file contents, a fabricated
`EXPENSES_OK` test run, the real file never touched -- see
`evidence/pi_agentic_debug.log`). Root cause, isolated by elimination:

- Not the "Model not found for provider... using custom model id" warning --
  the identical warning fires for every derived pinned tag used this session
  (verified against `gemma4-26b-e9pin-...`, which works fine with tools).
- Not an Ollama capability flag -- `/api/show` reports
  `capabilities: ['tools', 'thinking', 'completion']`, same shape as
  `gemma4:26b` and `gpt-oss:120b`, both of which use tools correctly.
- **It is the model's own chat template.** The template (visible via
  `/api/show`) has real machinery for rendering tool calls the assistant
  already made and tool outputs already returned, using DeepSeek's own
  special tokens (`<｜tool▁calls▁begin｜>` etc.) -- but no block anywhere
  injects the *available* tools into the prompt for a fresh turn.
- **Confirmed directly**, bypassing `pi` entirely: a raw call to
  `/v1/chat/completions` with a real `read_file` tool definition and a full
  4000-token budget (so it wasn't cut off mid-thought) finished cleanly
  (`finish_reason: stop`) with the model stating it had no file access at
  all. The tool was in the request; the model was never told about it.

No client-side fix (`pi` flags, `~/.pi/agent/models.json` registration) can
work around this -- the model genuinely never sees what tools exist, no
matter who is asking.

## 4. Raw coding capability, sidestepping the tool problem entirely

To separate "can't use tools" from "can't code," the actual
`csv-summarize-repair` fixture content was inlined directly into a single-shot
prompt (no tools required, matching the Alignerr benchmark's `--no-tools`
pattern) -- full file + full test file text, asked to output the corrected
function in one shot.

**Result: incorrect.** The model produced plausible, well-structured code,
but used a naive `line.split(',')` -- exactly the trap this task's own
docstring calls out ("quoted amounts... breaks on quoted amounts"). The
quoted field `"$1,234.56"` splits into `'"$1'` and `'234.56"'`, and the model's
code never accounts for this. Verified against the real test:
`AssertionError: food=46.44 expected 1280.00`.

**Follow-up: given the exact failure, still incorrect.** Fed the precise
`AssertionError` back in a second single-shot turn and asked to fix it. The
model changed `parts[2]` to `parts[-1]` -- a plausible-looking patch that
shifts which broken fragment gets parsed, not a fix for the actual cause
(the split needs to be quote-aware). Verified against the real test again:
`AssertionError: food=280.0 expected 1280.00`, still wrong.

Full transcripts and generated code: `evidence/r1_singleshot_result.json`,
`evidence/r1_followup_result.json`.

## Conclusion

Not just a harness casualty. With the tool-use problem completely sidestepped
(all content handed to it directly, one full round of ground-truth feedback
given), the model still did not converge on the actual bug. Combined with the
slowest decode speed characterized this session (17.9 tok/s) and mandatory,
unsuppressible thinking overhead, this model underperforms every other model
characterized this session on every axis measured: correctness, speed, and
harness compatibility. Screened and parked -- not run through the full E9
battery, since the failure modes found here (broken tool template, weak
single-shot correctness) would make a 30-cell run non-informative. Model
deleted from local storage after this record was written.

## Limits

- Single task (`csv-summarize-repair`), two single-shot turns, n=1 each --
  not a statistically powered result, just a screening characterization.
- The specific GGUF/template combination pulled via `ollama pull
  deepseek-r1:70b` may not represent every distribution of this model; a
  different quant/source could plausibly ship a corrected template. Not
  checked.
- Native DeepSeek-R1 (the actual MoE architecture) was not tested here --
  this is the Llama-70B distillation only. The tool-template defect and
  dense-KV-cache trap are specific to this checkpoint, not necessarily to
  DeepSeek-R1 generally.
