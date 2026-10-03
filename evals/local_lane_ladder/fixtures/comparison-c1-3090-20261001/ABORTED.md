# ABORTED — operator-side source edit, not a model or serving fault

2026-10-01 ~06:20 UTC. The Qwen35 quality packet stopped at cell 60 of 90 with
`RuntimeError: frozen input changed: run_standard_packet.py`. Cause: the
supervising agent edited `run_standard_packet.py` (Z13 UMA gate wiring) while
this packet was running. The fail-closed hash gate refused the next cell, as
designed. The edit was reverted to the frozen bytes (manifest hashes re-verified)
but per protocol there is no resume.

Preserved as evidence only: canary (3/3 qualified), decode (DECODE_FAILED: third
measured call stopped at 24 tokens), 59 recorded quality cells. **Not scored and
never pooled** with the rerun. The whole cohort reruns from scratch in
`comparison-c1-3090-20261001-r2/`. Gemma26 had not started; native Fusion had not
started (chain correctly refused without DONE).
