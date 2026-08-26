#!/usr/bin/env python3
"""Submit frozen SDXL text-to-image jobs to a running local ComfyUI server.

Start ComfyUI separately, e.g.:
  cd /home/blueaz/Python/Evaluation/ComfyUI && python main.py --listen 127.0.0.1 --port 8188

This script writes API workflow JSONs and queue receipts. Fetching image files is
left to ComfyUI's normal output directory plus the receipts/history.
"""
from __future__ import annotations

import argparse, json, random, urllib.request
from pathlib import Path


def workflow(prompt: str, seed: int) -> dict:
    return {
        "3": {"class_type": "KSampler", "inputs": {"seed": seed, "steps": 8, "cfg": 7.0, "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0, "model": ["4", 0], "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["5", 0]}},
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"}},
        "5": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 512, "batch_size": 1}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["4", 1]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "blurry, unreadable, malformed text, extra limbs, distorted wheels, photorealistic, caption-only joke", "clip": ["4", 1]}},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
        "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "comfy_symbolic_ats_elephant", "images": ["8", 0]}},
    }


def post_json(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode())


def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument("prompt_manifest", type=Path); ap.add_argument("--server", default="http://127.0.0.1:8188"); ap.add_argument("--seed-base", type=int, default=1191900); args=ap.parse_args()
    run_dir=args.prompt_manifest.parent
    manifest=json.loads(args.prompt_manifest.read_text())
    receipts=[]
    for i,row in enumerate(manifest["results"]):
        prompt=(run_dir/row["prompt_path"]).read_text().strip()
        seed=args.seed_base+i
        wf=workflow(prompt, seed)
        wf_path=run_dir/f"{row['label']}.workflow_api.json"; wf_path.write_text(json.dumps(wf,indent=2))
        receipt=post_json(args.server.rstrip("/")+"/prompt", {"prompt": wf})
        receipts.append({"label":row["label"],"model":row["model"],"seed":seed,"workflow":wf_path.name,"receipt":receipt})
        print(row["label"], receipt)
    (run_dir/"render_receipts.json").write_text(json.dumps(receipts,indent=2))
    return 0
if __name__ == "__main__": raise SystemExit(main())
