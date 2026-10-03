# pi on Terminal-Bench 2.1 with local models (5-task smoke, 2026-10-01/02)

**Status:** real, evidence-backed smoke runs, one attempt per task per run. Not a
benchmark claim: N=5, the tasks are the cheapest five from Stella's published run
(not a random sample), and every run used a single sample at non-zero
temperature. Useful as a **setup recipe** for running local Ollama models through
pi inside Harbor, and as a first signal on which local seat can carry
Terminal-Bench-shaped work.

This is **not** a pi-vs-Stella comparison. See `../stella_vs_pi_smoke/` for that
(August, GLM-5.2 via OpenRouter, pi 5/5 vs Stella 3/5 on the same five tasks).

## Result

| Run | Model (Testbench GPU 0, Ollama 0.32.12) | pi settings | Passed |
|---|---|---|---|
| August reference | `openrouter/z-ai/glm-5.2` | pi 0.84.3 defaults | **5/5** ($0.52) |
| `local-qwen36` | `qwen3.6-35b-interactive-ctx32768` (num_ctx 32768) | pi defaults | 2/5 |
| `local-qwen36-limits` | same | 32k window, 4k output cap | 2/5 |
| `local-qwen36-nothink` | same | 32k window, 4k cap, thinking off | 2/5 |
| `local-qwen38-64k-nothink` | `depth65536-qwen38` (qwen3.8 27B Q4_K_M, num_ctx 65536, 17.5 GB fully in VRAM) | 64k window, 8k cap, thinking off | **4/5** |

All local runs: pi 1.0.0 (Harbor installs `@latest` in each container), Harbor
0.22.0, dataset `terminal-bench/terminal-bench-2-1@sha256:7d7bdc1c...`, tasks run one
at a time, Harbor's default per-task timeouts, $0.

Per task (pass = verifier reward 1.0):

| Task | August GLM-5.2 | qwen3.6 32k (3 variants) | qwen3.8 64k, thinking off |
|---|---|---|---|
| `fix-git` | pass | pass, pass, pass | pass (64 s, 8 turns) |
| `prove-plus-comm` | pass | pass, pass, pass | pass (156 s, 28 turns) |
| `extract-elf` | pass (hit 900 s timeout) | fail, fail, fail | **pass** (216 s, 27 turns, peak input 30.4k) |
| `distribution-search` | pass | fail, fail, fail | **pass** (433 s, 40 turns, peak input 33.5k) |
| `polyglot-rust-c` | pass | fail, fail, fail | fail (528 s, 49 turns) |

The two tasks the 64k run newly passed peaked at 30.4k and 33.5k input tokens:
past a 32k window, inside 64k. Every task in that run ended on a normal stop (no
`length` stops, no compactions). `polyglot-rust-c` ended with the model reporting
that it could not produce a file that compiles as both Rust and C, rather than
handing over a broken one.

## Setup findings (the reusable part)

Each fix below removed one failure and exposed the next; the pass count on the
32k model never moved. Each is confirmed by a transcript or a direct request, as
noted.

1. **A spending-capped OpenRouter key rejects every pi 1.0.0 request.** pi asked for
   up to ~942k output tokens per request; OpenRouter pre-authorizes that against
   the key limit (about $3.76 at GLM-5.2's $3.99/M output) and returned HTTP 402
   before any generation. A $1-capped key scored 0/5 with zero tokens
   (`evidence/pi-smoke-5task-2026-10-01-latest/`). That is why the local runs exist.
2. **pi assumes 128k context and 16,384 output tokens for a custom model** that does
   not declare limits (pi 1.0.0 `model-config`: `contextWindow ?? 128e3`,
   `maxTokens ?? 16384`). It therefore never compacts against a 32k Ollama model.
   On `extract-elf` the model dumped the whole binary as hex, the conversation
   outgrew the window, and the next reply had lost the system prompt and task
   ("The user wants me to identify the file type from a binary dump"). Fix: declare
   `contextWindow` equal to Ollama's `num_ctx`.
3. **Ollama ignores `max_completion_tokens`**, which pi sends to generic
   OpenAI-compatible endpoints. Direct test: a cap of 20 returned 1053 tokens;
   `max_tokens: 20` returned 20. Without it, one `polyglot-rust-c` reply ran to
   31,024 output tokens and filled the window. Fix: `compat.maxTokensField:
   "max_tokens"`.
4. **A reply stopped with `length` ends the pi run.** pi treats it as a finished
   turn when it carries no tool call. In `local-qwen36-limits` all three failures
   ended this way: `extract-elf` and `polyglot-rust-c` on replies cut at exactly
   4,096 tokens, `distribution-search` on a 1,414-token reply with 29k of input,
   i.e. the context filling, not the cap. In `local-qwen36-nothink`, `extract-elf` and `polyglot-rust-c` ended when
   the conversation reached ~28-29k and Ollama stopped the reply with `length` (pi
   compacted once in `polyglot-rust-c`, not at all in `extract-elf`). Not verified in
   pi's source: why compaction did not keep these runs further under 32k.
5. **qwen3.6's thinking only responds to `reasoning_effort: "none"`.** Direct test on a
   one-sentence question: unset 8,121 reasoning chars, `high` 3,084, `low` 4,668,
   `none` 0. pi sends it when the model is declared `reasoning: true` with
   `thinkingLevelMap: {"off": "none"}` and `compat.supportsReasoningEffort: true`, and
   Harbor's `thinking: "off"` agent kwarg is set.
6. **Declaring `reasoning: true` makes pi send the system prompt as the `developer`
   role**, which qwen3.8's Ollama template rejects (HTTP 500 on every request;
   `evidence/ABORTED-...-developer-role/`). qwen3.6's template accepted it. Fix:
   `compat.supportsDeveloperRole: false`.

`harbor_pi_local.py` is the agent wrapper that applies 2, 3, 5 and 6. Harbor writes
pi's `models.json` with only the model id, so the wrapper subclasses Harbor's pi
agent and adds the fields. It reads `PI_LOCAL_CONTEXT_WINDOW` (default 32768) and
`PI_LOCAL_MAX_TOKENS` (default 4096).

The wrapper grew run by run; the copy here is the final version:

| Run | Wrapper state |
|---|---|
| `local-qwen36` | none (Harbor's built-in pi agent) |
| `extract-elf ... -limits` (1 task) | `contextWindow`, `maxTokens` only (cap not enforced, finding 3) |
| `local-qwen36-limits` | + `compat.maxTokensField` |
| `local-qwen36-nothink` | + `reasoning`, `thinkingLevelMap`, `supportsReasoningEffort` |
| `ABORTED-...-developer-role` | + env-configurable limits (65536 / 8192) |
| `local-qwen38-64k-nothink` | + `supportsDeveloperRole: false` (final) |

## Reproduce

Harbor task containers cannot reach Desktop's 127.0.0.1 Ollama tunnels, so the runs
used a temporary tunnel bound to the Docker bridge (stop it afterwards; while it
is up any local container can reach Testbench's Ollama):

```sh
systemd-run --user --unit=harbor-testbench-ollama-tunnel /usr/bin/ssh -N \
  -o BatchMode=yes -o ExitOnForwardFailure=yes \
  -L 172.17.0.1:11462:127.0.0.1:11434 testbench

cd ~/Python/Evaluation/pi-mono      # Harbor venv lives here
cp ~/operator-control-plane/evals/pi_tb21_local_smoke/harbor_pi_local.py .
PI_LOCAL_CONTEXT_WINDOW=65536 PI_LOCAL_MAX_TOKENS=8192 PYTHONPATH=. \
  .harbor-venv/bin/harbor run -c \
  ~/operator-control-plane/evals/pi_tb21_local_smoke/configs/pi-smoke-5task-2026-10-02-local-qwen38-64k-nothink.config.json

systemctl --user stop harbor-testbench-ollama-tunnel
```

Configs are in `configs/`. The 64k config was used for both the aborted run and
the final run; only the wrapper differed. Configs carry a dummy
`OLLAMA_API_KEY` and no real credential.

## Evidence

- `evidence/<run>/` per trial: `config.json`, `result.json`,
  `verifier/test-stdout.txt`, `verifier/reward.txt`, and `agent_stats.json` (turns,
  peak input/output per turn, `length` stops, thinking chars, compactions, first
  error) derived from pi's transcript.
- Full transcripts (`agent/pi.txt`, ~0.1-0.6 MB each) stay in the raw job dirs:
  `~/Python/Evaluation/pi-mono/.harbor-jobs/<run>/`.
- `python3 collect.py [JOBS_DIR]` re-copies the evidence from those dirs and prints
  every number in this README.

## Next, if picked up

- Repeat the 64k run (several samples per task) before reading 4/5 as stable.
- Check how pi 1.0.0 decides when to compact (finding 4).
- If pi vs Stella matters again, run both on the same tasks on the same day; the
  August Stella numbers are from Stella's own 2026-07-31 run.
