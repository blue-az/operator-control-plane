# "31/31 layers on GPU" does not mean the model is on the GPU

**Instrument fault. Discovered 2026-09-12 02:52, desktop (i9-9900KF, 15.9 GB,
RTX 2080 8 GB), ollama 0.32.12, driver 580.178.04.**

`gemma4:26b` is an MoE model. On this card ollama moves **every expert tensor to
system RAM** and keeps only dense weights on the GPU — and then logs
`load_tensors: offloaded 31/31 layers to GPU`. The layer counter counts *layers*,
not *experts*. For an MoE model it reads as full residency while the bulk of the
weights are on the host.

Every published 2080 figure in this program was measured in that state.

## 1. Raw load decisions

Ollama's own fitting pass, verbatim (`journalctl -u ollama`):

    common_params_fit_impl: projected to use 16628 MiB of device memory
                            vs. 6903 MiB of free device memory
    common_params_fit_impl: cannot meet free memory target of 2170 MiB,
                            need to reduce device memory by 11895 MiB
    common_params_fit_impl: context size set by user to 4096 -> no change
    common_params_fit_impl: getting device memory data with all MoE tensors
                            moved to system memory:
    common_params_fit_impl: with only dense weights in device memory
                            there is a total surplus of 1575 MiB

Immediately after, in the same load:

    load_tensors: offloading output layer to GPU
    load_tensors: offloading 29 repeating layers to GPU
    load_tensors: offloaded 31/31 layers to GPU

**Both lines are true and they describe different things.** 31/31 dense layers
are on the GPU. All MoE experts are not.

## 2. Required vs free VRAM — every load, not a near miss

| time | projected need | free device memory | decision |
|---|---:|---:|---|
| 09-11 20:19 | 16,469 MiB | 6,478 MiB | experts -> system RAM |
| 09-11 20:23 | 16,880 MiB | 7,224 MiB | experts -> system RAM |
| 09-11 21:08 | 16,880 MiB | 7,413 MiB | experts -> system RAM |
| 09-11 21:56 | 16,880 MiB | 7,387 MiB | experts -> system RAM |
| 09-11 22:34 | 16,628 MiB | 7,385 MiB | experts -> system RAM |
| 09-11 22:37 | 16,628 MiB | 7,385 MiB | experts -> system RAM |
| 09-11 22:45 | 16,880 MiB | 7,403 MiB | experts -> system RAM |
| 09-12 00:09 | 16,880 MiB | 6,838 MiB | experts -> system RAM |
| 09-12 00:28 | 16,628 MiB | 7,003 MiB | experts -> system RAM |
| 09-12 02:52 | 16,628 MiB | 6,903 MiB | experts -> system RAM |

Model blob on disk: **17.33 GB**. Card: 8,192 MiB total. The shortfall is
**~11.5 GB on every load**. This model has never been GPU-resident on this card
and cannot be. Free-VRAM variation (6,478-7,413 MiB) never changed the outcome.

## 3. Decode, iowait and page faults — cached vs evicted

Speed is set by whether host RAM can cache the expert tensors, which are mmap'd
from the model file. Placement is identical in both phases.

**Evicted phase** (2026-09-12 ~02:55, Chrome resident at 6.3 GB, free RAM 305 MB,
swap 0/0 so no swapping involved):

    decode            4.0 - 4.5 tok/s
    pgmajfault        74,312 over 128 tokens   (~580 major faults per token)
                      52,816 over 96 tokens
                      36,797 over 96 tokens
    bi (blocks in)    1,263,604 - 1,657,192 per second, sustained
    wa (iowait)       33 - 41%
    si (swap-in)      0
    prefill           3.8 tok/s

**Cached phase** (2026-09-11 21:00-23:00, Chrome closed, host RAM free):

    decode            32.2 - 34.2 tok/s across 9 benchmark trials
    same placement    all experts in system RAM (rows in section 2)

**8x difference at identical GPU placement.** `si=0` throughout the evicted phase
proves this is page-cache miss to disk, not swap. The model file is mmap'd; when
the page cache cannot hold the expert tensors they are re-read per token.

This also explains the degradation observed across 2026-09-11 benchmark runs,
where decode fell 33.5 -> 33.3 -> 19.8 -> 10.5 tok/s within a single 4-trial run
as zram filled: expert pages being evicted progressively, not the GPU changing.

## 4. Layer placement vs MoE expert residency — the distinction

| evidence source | what it reports | what it does NOT report |
|---|---|---|
| `load_tensors: offloaded N/N layers` | dense layer placement | expert tensor placement |
| `ollama ps` PROCESSOR column | derived from size_vram/size | nothing reliable (see below) |
| `/api/ps` `size` / `size_vram` | wrong by ~13x on this model | actual footprint |
| `nvidia-smi` per-process VRAM | true device allocation | which tensors are where |
| `common_params_fit_impl` log | **the actual decision** | — |

`/api/ps` for this model reported `size: 1,311,359,630` (1.22 GB) and
`size_vram: 988,115,107` (0.92 GB) while `nvidia-smi` showed the process holding
**7,202 MiB**. The derived "25%/75% CPU/GPU" split is arithmetically correct from
two wrong numbers. `parameter_size: "25.2B"` in the same payload is correct, so
the metadata is right while the memory fields are not.

**Only the `common_params_fit_impl` block, or a per-device VRAM measurement
against the model's known full-residency requirement, establishes MoE residency.**

## 5. Scope — what is and is not affected

**Affected:** every RTX 2080 figure in this program. `testbench-2080-fit-check`
publishes `gemma4:26b | MoE | 31 of 31 | 7,416 MiB | 31.02 tok/s`, which reads as
full residency and was not.

**Not affected by this mechanism:** the same fixture's `qwen3.8:27b | dense |
16/66 | 6,438 MiB | 3.80 tok/s`. That model is dense, so the layer counter is
meaningful and the row is sound as published.

**Unverifiable from existing artifacts:** the Ryzen AI MAX 390 (z13) MoE rows.
No `fit_impl` evidence was captured in any z13 fixture. The z13 is an APU with
unified memory, where the device/host distinction differs fundamentally, so the
question may not even be well-posed in the same terms. **It cannot be confirmed
or denied from what was recorded** and needs a fresh load with the fit log
captured.

**Correctness is unaffected.** Quality results stand on their own axis: the 2080
recorded 15/15 on the E9 L2 battery and 17/18 across 2026-09-11 runs. Mixed
placement changes how fast a row was produced, not whether it was right.

## 6. Consequence for the placement gate

`GOLD_STANDARD.md` §"Placement must be captured" already rules `/api/ps` alone
insufficient and requires "daemon-specific offloaded N/M logs". **That
requirement is now also insufficient for MoE models**, because the N/M line is
exactly what misreports here.

Gate change required: for MoE models, neither `ollama ps` `size_vram`/`size` nor
`offloaded N/N layers` is authoritative residency evidence. A row claiming GPU
residency for an MoE model needs the load-time fitting decision or an equivalent
per-device VRAM measurement checked against the model's full-residency
requirement.

**No MoE "100% GPU" claim may be published from layer-count output alone.**
