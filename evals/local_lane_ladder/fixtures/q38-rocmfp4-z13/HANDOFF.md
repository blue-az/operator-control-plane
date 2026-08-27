# Handoff — Mei Ling ROCmFP4 on z13 + LinkedIn wrap

**Date:** 2026-08-17
**Author:** grok (this session). Do not self-verify the numeric claim.
**Machine split (Front H):** decode numbers were measured on **z13**. This file and the opr task live on the **desktop** ledger. Do not merge `.operator/` trees.
**opr task:** `q38-rocmfp4-z13-mei-ling`

Read this file first. Then `cd ~/operator-control-plane && ./operator task-show q38-rocmfp4-z13-mei-ling`.

---

## What just happened

Mei Ling Leung posted Qwen 3.8 27B at ~26 tok/s (32 peak) on a **Max+ 395 / 8060S 40 CU / 128 GB** custom `q38rocm` stack (ROCmFP4 + MTP + TurboQuant KV + RADV Wave64). She @-mentioned Erik and said try ROCmFP4.

We ran her stack on **z13** (Max **390 / 8050S 32 CU / 27 GB**, 17.5–24 GiB GPU-addressable, Vulkan RADV). Isolated dir. Ollama seat was not replaced.

**Result:** it loads. It does not beat the existing Ollama seat.

| 8k, Qwen 3.8 27B, same 390 | tok/s |
|---|---:|
| Ollama `qwen38-mtp-2` (eval_count/eval_duration, 128 gen, 2026-08-17) | **21.6** warm (t2/t3 20.7+20.4 stock; mtp-2 23.0+20.1) |
| ROCmFP4 Vulkan MTP **n=2** (llama-cli TUI Generation, 128 gen) | **21.4 / 22.8** |
| ROCmFP4 Vulkan MTP **n=4** n=5 clean | **17.4 17.7 17.4 17.8 18.2** mean **17.7** |
| ROCmFP4 Vulkan no MTP (`llama-bench` tg128) | **12.6** |

n=2 ties Ollama. n=4 is worse (same shape as paper 1.44 / stock draft 4 too deep). 4k does not help. Do not switch the daily seat.

Erik's standing z13 **26b** decode today was **55–58** (published field 51.3). That is a different model (MoE). Do not put 26b in the Mei Ling 27B table.

---

## Artifacts

**z13 (do not delete unless the user says so)**

- `/home/blueaz/models/q38rocm/` — 14 GB. `julianmb/q38rocm` clone, prebuilt engine v1.0.0, `Qwen3.8-27B-ROCmFP4-FAST.gguf` SHA256 `fb89c78d2be91cdb68eaaaa45b1270710bf34aa721dc1f0b9e3aa7b98d2e1da9`
- Engine needs `LD_LIBRARY_PATH=.../engine/bin:/usr/local/lib/ollama/rocm_v7_2` (distro HIP is 6.4; prebuilt wants hipblas.so.3 from Ollama's ROCm 7.2 bundle)
- Vulkan ICD on Fedora: `/usr/share/vulkan/icd.d/radeon_icd.x86_64.json` (upstream `setup_env.sh` points at a Debian path and is wrong here)
- `llama-cli -no-cnv` is rejected; use `-st` (single-turn). TUI `Generation:` lines only appear on a real tty — use tmux `pipe-pane`
- Logs copied here: `n4.pane`, `rerun.pane`, `z13-bench2.log`

**desktop**

- `/home/blueaz/Public/LinkedIn/rocm-vs-ollama.png` — comment image (ROCmFP4 vs Ollama, same 390)
- `/home/blueaz/Public/LinkedIn/max395-vs-max390.png` — hardware compare (395 vs 390). User did **not** want this for the Mei Ling comment
- Box-drawing Unicode will not paste into LinkedIn comments or LibreCalc. Use the PNG

**Take-over**

- `ssh z13` works. Idle leftover tmux: `q36-35b-e9-z13` (done), `z13-l2` (L2 already finished). Do not attach those unless asked
- Power: AC=1, `platform_profile=balanced`, `scaling_governor=powersave`, `powerprofilesctl set performance` is DBus AccessDenied. Label AC+powersave. 26b at 56 means this is **not** the 13.7 battery hole
- Do not run `apply_hardware_tweaks.sh` (sudo)

---

## LinkedIn state

Posted by Erik this thread:

- Nune Isabekyan: Gemma4 3090 comment, then HUHE reply (Hardware / Use Case / Harness / Expectations). Harness sentence kept the model line: choosing a model is generally by performance; harness depends on workflow
- Brian Perron named Erik as Gemma-4 26B advocate **without an @**, so no notification. Third-beat comment was outlined (thanks + OpenRouter + OpenCode as free local harness, no Zen) — **not confirmed posted**
- Mei Ling: table PNG ready; **reply not written unless the user asks**. Do not draft Erik's voice unless asked

OpenCode local (`ollama/gemma4:26b` @ localhost:11434) has **no API usage**. Hy3 Free is Zen promo, different path.

---

## Constraints for the next agent

- Do **not** extra-run Qwen L0/L1/L2 ladder cells
- Do **not** mass-edit operator-control-plane
- Do **not** merge z13 and desktop ledgers (Front H)
- Do **not** replace Ollama with ROCmFP4
- Do **not** publish the z13 L2 12/18 unless the user asks (public page still says L2 transferred)
- User pastes, agent sets files. One political post/week. Keep Stephen Miller wink
- `opr --dangerous` does not waive frontier `input()`

---

## Open (ask before acting)

1. Reply to Mei Ling with `rocm-vs-ollama.png`?
2. Delete `/home/blueaz/models/q38rocm` (14 GB, disk 90%)?
3. Post the Brian third beat?
4. Update bulkhead-tau local-lane: z13 L2 **was** run 36/36, both models 12/18
5. Sell-or-keep second 3090 / 70B after the cord

## First recommended action

`./operator task-show q38-rocmfp4-z13-mei-ling` then wait. The measurement is done. Next move is the user's comment, not more decode.
