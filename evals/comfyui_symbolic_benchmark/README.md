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

## Repeatable run path

The repeatable scaffold is now present:

1. Generate one prompt per local text model:

   ```bash
   python evals/comfyui_symbolic_benchmark/generate_prompts.py
   ```

2. Start local ComfyUI separately with the SDXL checkpoint available:

   ```bash
   cd /home/blueaz/Python/Evaluation/ComfyUI
   python main.py --listen 127.0.0.1 --port 8188
   ```

3. Submit fixed SDXL workflow jobs:

   ```bash
   python evals/comfyui_symbolic_benchmark/render_comfyui_sdxl.py <run_dir>/prompt_manifest.json
   ```

4. Copy resulting images from the ComfyUI output directory into the run directory, hash them, and score them in `score_sheet.csv`.

## Status

This is currently an artifact-scored benchmark plus a repeatable scaffold. It becomes fully rerunnable once a ComfyUI render run is completed from the generated prompt manifest. The white paper still lists missing historical items: original full ComfyUI session log, original workflow JSON, exact frontier model/prompt, and a second-hardware reproduction.

## Scoring

Each image is scored 0/1 on the four symbolic constraints. The benchmark records both raw model output and harness-assisted/composited output separately. Caption-only rescue is marked as harness assistance, not raw model success.
