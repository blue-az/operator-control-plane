# Incident: repeated freeze running sglang NVFP4 tensor-parallel on dual RTX 3090 (desktop)

Written by Claude (z13 session) for luna to pick up. 2026-08-28.

## What happened

Desktop hard-froze twice tonight running:

```
sglang.launch_server --model-path /home/blueaz/models/Qwen3.8-Flash-Next-NVFP4 \
  --tp-size 2 --quantization modelopt_fp4 --fp4-gemm-backend flashinfer_cutlass \
  --moe-runner-backend auto --cpu-offload-gb 4 --page-size 64 \
  --context-length 2048 --mem-fraction-static 0.70 \
  --disable-custom-all-reduce --disable-cuda-graph --skip-server-warmup \
  --host 127.0.0.1 --port 30000
```

**First crash** (~13:55–16:03): kernel log showed repeated `NVRM: Out of memory`
VRAM alloc failures and repeated `Xid 31` MMU faults tied to a separate
`llama-server` process running concurrently with `sglang`, then a system-RAM
OOM-kill of an `sglang::schedul` process at 16:03 (dozens of Chrome tabs were
also open at the time).

**Second crash** (~18:30–18:36, sglang run alone, nothing else): live-polled
`free`/`swapon`/load every 10s. Swap usage climbed steadily the whole time —
47GB → 110GB+ — even with no other program running and a short 2048-token
context. Available RAM collapsed from ~5GB to 84MB over the last 90 seconds,
load average spiked from ~4 to 35.66, then the box stopped responding
entirely (SSH banner timeout, had to hard power-cycle).

Desktop specs: i9-9900KF, 32GB RAM (down from 64GB after two sticks died
in an earlier PSU incident), 2x RTX 3090 (24GB each, no NVLink, PCIe-only
interconnect with a x4-lane bottleneck on the second slot — see
`machines/desktop/ISSUES.md` in the dotfiles repo), root disk at 97% full.

## My hypothesis (unverified — needs your eyes on the actual box)

**NVFP4 needs native Blackwell (SM100) tensor cores. The RTX 3090 is Ampere
(SM86) and has no native FP4 path at all.** Running `modelopt_fp4` via
`flashinfer_cutlass` on a 3090 must be going through some dequantize-to-fp16/
bf16 compatibility path, not a real fast path. The launch flags already show
someone fighting that incompatibility before tonight: `--disable-cuda-graph`
and `--disable-custom-all-reduce` are the kind of thing you only turn off
when the normal path crashes on unsupported hardware.

That fits the crash shape better than a plain "model too big" OOM would: a
hard ceiling plateaus immediately; this instead climbed steadily for six
minutes with a static server and no traffic, which looks like a leak in the
loading/init or FP4-shim path rather than a one-time size mismatch.

Separately: even if stabilized, the two 3090s aren't NVLinked and the second
PCIe slot is chipset-limited to x4 lanes (documented pre-existing concern in
this same desktop's GPU-expansion project), so `--disable-custom-all-reduce`
would make tensor-parallel all-reduce traffic slower still.

## What I'd like you (luna) to check, with actual shell access to the box

1. Pull the full `sglang` **startup log** (not just kernel log) from either
   crash — look for any explicit warning about unsupported/emulated FP4 on
   this GPU architecture.
2. Confirm the real size of `/home/blueaz/models/Qwen3.8-Flash-Next-NVFP4`
   (`du -sh`, and its `config.json`) — total params, active params if MoE,
   and what memory footprint that implies at 4-bit vs. what `--cpu-offload-gb`
   is actually meant to cover.
3. Test the **same model** (or closest available quant) in a **non-NVFP4**
   format — AWQ/GPTQ INT4 or a GGUF Q4 via llama.cpp — under the same
   `--tp-size 2` dual-3090 setup, with a memory watchdog this time (kill the
   process if swap usage crosses e.g. 60GB, so it can't take the box down
   again). Does memory stay bounded?
4. Report back: is NVFP4 tensor-parallel inference viable on this hardware
   at all, or should it be abandoned for a different quant format? Please
   write the answer back into this file (or reply however you and Erik have
   been relaying results) rather than only reporting in chat — this file is
   git-synced across machines via `bnsync`, so anything you leave here is
   visible from other sessions too.

**Do not relaunch the exact same command unattended** — put a memory/swap
ceiling and an automatic kill switch around any dual-3090 sglang test before
running it again. Two hard freezes in one evening from the same launch
config is enough.
