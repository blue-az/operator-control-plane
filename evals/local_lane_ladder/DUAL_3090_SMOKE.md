# Multi-GPU configs — mixed 2080, dual 3090, open testbench

**Status:** plan 2026-08-13 (corrected: mixed partner is **RTX 2080**, not 4090).  
**Blockers:** second PSU in hand (return first when packed/sent); E10 420-cell finish before stealing desktop GPU.  
**Script (dual-resident / inventory):** `scripts/smoke_mixed_gpu.sh` — retarget models if 2080 is 8 GB (14b may not fit).

---

## Three setups (all intended once 2nd PSU exists)

| Config | Hardware | Role | “Win” if… |
|--------|----------|------|-----------|
| **A. Mixed daily** | **3090 + 2080** (same case) | Preferred lifestyle: LLM + 1080p + lower draw | 3090 holds E9 seats at full speed; 2080 handles display/game; optional tiny offload only if clean |
| **B. Dual 3090 capacity** | **2× 3090** (desktop or open bench) | True dual-weight / fat ctx | nemotron ~25 GB / ~32–35B Q4 **no CPU spill** at stated `num_ctx` |
| **C. Open testbench** | Same mobo on W01 (or similar) + whichever GPUs | Smoke / dual bring-up without fighting daily case | POST, both GPUs, PSU rails, short residency runs |

**A and B are different products.** A is not a cheap dual-3090. B is not the daily power story. C is the **bring-up path** so you can validate B without committing the living-room box.

Return PSU #1 → receive/use PSU #2 → then A/B/C are all physically possible (swap cards, open bench, or both).

---

## Expectations (so benchmarks have a hypothesis)

### A — Mixed 3090 + 2080 (“best of both worlds”)

| Expect | Detail |
|--------|--------|
| **Daily LLM** | Still **3090-only** for 14b/26b/31b — same E9 quality/latency |
| **2080** | 8 GB (or 11 Ti): games @ 1080p, desktop; **not** a peer for 35B |
| **Layer-split mid models across both** | Often **slower** than 3090 alone (Turing slice + PCIe) |
| **Dual-resident** | Big seat on 3090; small seat on 2080 **only if it fits** (7–8B class on 8 GB; 14b needs Ti + tight ctx or fails) |
| **35B / nemotron** | **Do not promise**; maybe ugly load, likely spill/crawl |
| **Power / sell** | Lower than dual 3090 when not dual-loading; sell **extra** 3090 only if you **keep** the 24 GB card for AI |

**Bench question for A:** *Is lifestyle better (power, gaming, noise) without losing 3090-only agent latency?*  
Not: *Does 35B crush E9?*

### B — Dual 3090

| Expect | Detail |
|--------|--------|
| **Capacity** | Real dual win: **~48 GB class**, nemotron / fat 32–35B Q4 + usable ctx |
| **Ranking** | May **not** beat single-3090 26b on E9 wall time |
| **Power** | Two × ~350 W class under load — the cost of capacity |
| **Dual-resident** | 26b + 14b (or 26b + 31b) on two instances — strong |

**Bench question for B:** *What loads that single 3090 cannot host cleanly?*

### C — Open testbench

| Expect | Detail |
|--------|--------|
| **Use** | Dual 3090 POST, PCIe width, PSU headroom, short S1–S3 smokes |
| **Risk** | Card sag, open-air dust, cable mess — fine for smoke, not forever |
| **Order** | Prefer **validate B on C**, then decide whether B stays in the daily case or stays bench-only |

---

## Bench matrix (minimal, comparable)

Shared controls when any ladder cells run: `think off`, `temp 0.8`, `num_ctx` recorded, traces, `OPERATOR_MACHINE=desktop` (or `testbench`), `ollama ps` sampling.

| ID | Config | Procedure | Pass criteria |
|----|--------|-----------|---------------|
| **M0** | A or B | `nvidia-smi -L`, PCIe gen/width, PSU note | 2 GPUs as intended |
| **M1** | A: 3090-only pin | `CUDA_VISIBLE_DEVICES=0` + one E9 cell `gemma4:26b` | Latency ≈ pre-mixed baseline |
| **M2** | A: dual-resident | 3090 big + 2080 small (if VRAM allows) | Both answer; no crash; note if 14b OOM on 2080 |
| **M3** | A: optional split | One mid model, both GPUs visible | Residency + wall vs M1 (expect M1 often wins) |
| **M4** | B: dual 3090 load | `nemotron-3.5-lightning` or similar ~25 GB | Load + **no CPU spill** at target ctx |
| **M5** | B: dual-resident | 26b + 14b on two ollama instances | Concurrent; both 100% GPU |
| **M6** | B optional | n=3 E9 subset on dual-only model | Only if M4 clean — quality note, not full matrix |

Do **not** run full 7×5×6 while validating hardware.

---

## Suggested order once 2nd PSU is live

1. **Finish or pause E10** cleanly (don’t dual-smoke under the 420-cell runner).  
2. **C (open bench) + dual 3090** short path: M0 → M4 → M5 (prove capacity).  
3. **A (mixed daily case)** M0 → M1 → M2 → M3 (prove lifestyle without regression).  
4. Decide: dual 3090 stays in bench vs case; whether a 3090 can be sold (**keep 24 GB for LLM**).  
5. File `fixtures/e11-mixed-smoke/` and/or `e12-dual3090-smoke/` FINDINGs + residency logs; UID re-derive if claiming.

Script today: `scripts/smoke_mixed_gpu.sh` (assumes two GPUs; dual-resident defaults 26b+14b — **override B to an 8B** on stock 2080 8 GB).

```bash
# example once hardware is up and runner idle
MIXED_MODEL_A=gemma4:26b MIXED_MODEL_B=llama3.1:8b \
  evals/local_lane_ladder/scripts/smoke_mixed_gpu.sh --check
# then full smoke
```

---

## One-line strategy

**Mixed 2080 = best daily (power + 1080p + 3090 LLM). Dual 3090 = capacity lab (testbench OK). Second PSU unlocks both; don’t expect the 2080 to deliver the 35B dual-3090 win.**
