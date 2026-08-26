#!/usr/bin/env python3
from __future__ import annotations

import argparse, json, os, subprocess, time
from pathlib import Path

MODELS = [("qwen38","qwen3.8:27b"),("qwen36-35b","qwen3.6:35b"),("gemma31","gemma4:31b"),("gemma26","gemma4:26b")]
INSTRUCTION = """Write one SDXL/ComfyUI positive prompt for this fixed benchmark task.
Do not explain. Output only the prompt text.

Task: editorial political cartoon where companies relying on ATS applicant tracking systems are represented as a huge corporate elephant riding and overloading a tiny child's tricycle. The metaphor must be legible from the image itself.

Must include visual cues for: elephant, tiny child's tricycle, severe scale/overload, ATS/hiring/company screening satire. Avoid relying on an external caption only.
"""

def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument("--out", default=None); ap.add_argument("--provider", default="ollama"); ap.add_argument("--ollama-host", default="127.0.0.1:11435"); ap.add_argument("--timeout", type=int, default=240); ap.add_argument("--models", default=",".join(x for x,_ in MODELS)); args=ap.parse_args()
    selected={x.strip() for x in args.models.split(",") if x.strip()}; models=[m for m in MODELS if m[0] in selected]
    out=Path(args.out) if args.out else Path(__file__).resolve().parent/"runs"/time.strftime("%Y%m%d-%H%M%S-prompts")
    out.mkdir(parents=True, exist_ok=True)
    env=os.environ.copy(); env["OLLAMA_HOST"]=args.ollama_host
    rows=[]
    for label, model in models:
        cmd=["pi","--provider",args.provider,"--model",model,"--thinking","off","--no-context-files","--no-session","--no-tools","--print","--",INSTRUCTION]
        print(f"PROMPT {label} {model}", flush=True)
        t=time.time(); p=subprocess.run(cmd,text=True,capture_output=True,timeout=args.timeout,env=env); elapsed=round(time.time()-t,3)
        prompt=p.stdout.strip()
        (out/f"{label}.prompt.txt").write_text(prompt)
        (out/f"{label}.json").write_text(json.dumps({"label":label,"model":model,"elapsed_s":elapsed,"returncode":p.returncode,"prompt":prompt,"stderr":p.stderr,"cmd":cmd},indent=2))
        rows.append({"label":label,"model":model,"elapsed_s":elapsed,"returncode":p.returncode,"prompt_path":f"{label}.prompt.txt"})
    (out/"prompt_manifest.json").write_text(json.dumps({"instruction":INSTRUCTION,"results":rows},indent=2))
    print(out)
    return 0
if __name__ == "__main__": raise SystemExit(main())
