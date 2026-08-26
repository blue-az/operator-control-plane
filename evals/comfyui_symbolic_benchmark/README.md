# ComfyUI Symbolic Constraint Benchmark

Local-only benchmark packet for Paper 1.19, "The Capability Ceiling".

## Thesis under test

For image-generation tasks that require several symbolic constraints to land at the same time, harnessing helps but cannot fully replace model capability. The failure mode is often not nonsense; it is a visually coherent image that misses the meaning-carrying constraint.

## Fixed task

Generate an editorial/political cartoon showing companies relying on ATS systems as:

1. recognizable elephant,
2. recognizable tiny tricycle,
3. elephant much larger than the tricycle and physically riding/overloading it,
4. hiring/ATS satire legible from the image itself, preferably without relying only on an external caption.

## Assets

Assets are copied from `/home/blueaz/Python/Evaluation/ComfyUI/output/` and hashed in `assets/SHA256SUMS.txt`.

Key artifact:

- `assets/frontier_vs_local_elephants_corrected.png` — side-by-side frontier vs local comparison used by the white-paper stub.

Local attempts included:

- `assets/ats_cartoon_12b_00001_.png`
- `assets/ats_cartoon_26b_00001_.png`
- `assets/ats_cartoon_hybrid_clean_00004.png`
- `assets/prompts_compare.json`

## Status

This is currently an artifact-scored benchmark, not a fully rerunnable generation benchmark. The white paper explicitly lists missing items: full ComfyUI session log, workflow JSON, exact frontier model/prompt, and a second-hardware reproduction.

## Scoring

Each image is scored 0/1 on the four symbolic constraints. The benchmark records both raw model output and harness-assisted/composited output separately. Caption-only rescue is marked as harness assistance, not raw model success.
