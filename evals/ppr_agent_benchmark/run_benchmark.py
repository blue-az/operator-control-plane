#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT_BASE = ROOT / "runs"
MODELS = [("qwen38","qwen3.8:27b"),("qwen36-35b","qwen3.6:35b"),("gemma31","gemma4:31b"),("gemma26","gemma4:26b")]
SOURCE = (ROOT / "sources" / "ppr_ground_truth.md").read_text()
TASKS = {
  "ppr1_product_boundary": """Task: Write a concise product-boundary briefing for PPR Agent. Preserve exact facts and avoid overclaiming.\nReturn sections: SURFACES, DATA_BOUNDARY, NON_GOALS, NUMBERS, RISK_NOTES.\nMust mention 4 surfaces, 15 tools, full vs published subset, 3576, 1483, 41.5%, not clinical monitoring, offline PDF ingestion, deterministic-not-chatbot.\n""",
  "ppr2_gate_query_semantics": """Task: Explain PPR Agent query/gate semantics and answer the two gate examples.\nReturn sections: RULES, GATE_RESULTS, QUERY_VS_GATE, FAILURE_MODES.\nMust mention RUL-001 precedence, RUL-002 normalization, RUL-003 year cap, mdt 2030 allowed/year_capped 2025/company MDT, st jude 2007 allowed/year_capped 2008/company null, query executes data and gate only inspects policy.\n""",
  "ppr3_real_data_report": """Task: Produce an analyst report from the PPR real-data facts.\nReturn sections: ICD_2023_COMPARISON, TOP_2023_DEVICES, MARKET_CONCENTRATION, SCOPE_LIMITS.\nMust include MDT vs ABT ICD 2023 exact model/family/implant numbers, top five 2023 devices with implant counts, HHI 3912.31 High, market shares MDT 52.96 ABT 24.42 BSX 22.61, and state this is historical analytical registry data not clinical advice.\n""",
}

def run_openai_compatible(model, prompt, timeout, base_url):
    url = base_url.rstrip("/") + "/chat/completions"
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": 2048,
        "thinking": {"type": "disabled"},
        "reasoning_effort": "none",
    }).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode()
        data = json.loads(raw)
        msg = data.get("choices", [{}])[0].get("message", {})
        return {"returncode": 0, "elapsed_s": round(time.time() - t, 3), "stdout": msg.get("content", ""), "stderr": "", "raw_response": data, "cmd": ["POST", url]}
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")
        return {"returncode": e.code, "elapsed_s": round(time.time() - t, 3), "stdout": "", "stderr": raw, "cmd": ["POST", url]}


def run_one(provider, model, prompt, timeout, host, base_url):
    if provider in {"openai-compatible", "freetoken"}:
        return run_openai_compatible(model, prompt, timeout, base_url)
    env=os.environ.copy(); env["OLLAMA_HOST"]=host
    cmd=["pi","--provider",provider,"--model",model,"--thinking","off","--no-context-files","--no-session","--no-tools","--print","--",prompt]
    t=time.time(); p=subprocess.run(cmd,text=True,capture_output=True,timeout=timeout,env=env)
    return {"returncode":p.returncode,"elapsed_s":round(time.time()-t,3),"stdout":p.stdout,"stderr":p.stderr,"cmd":cmd}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--provider",default="ollama"); ap.add_argument("--ollama-host",default="127.0.0.1:11435"); ap.add_argument("--base-url",default="http://127.0.0.1:1934/v1"); ap.add_argument("--served-model",default=None,help="Override model id sent to an OpenAI-compatible server, e.g. a FreeToken served-model-name."); ap.add_argument("--timeout",type=int,default=420); ap.add_argument("--models",default=",".join(x for x,_ in MODELS)); args=ap.parse_args()
    selected={x.strip() for x in args.models.split(",") if x.strip()}; models=[m for m in MODELS if m[0] in selected]
    out=OUT_BASE/time.strftime("%Y%m%d-%H%M%S"); out.mkdir(parents=True)
    manifest={"out_dir":str(out),"provider":args.provider,"ollama_host":args.ollama_host,"base_url":args.base_url,"results":[]}
    for task,p in TASKS.items():
        prompt=p+"\nUse only this local ground truth snapshot:\n"+SOURCE
        (out/f"{task}.prompt.txt").write_text(prompt)
        for label,model in models:
            print(f"RUN {task} {label} {model}",flush=True)
            request_model = args.served_model or model
            r=run_one(args.provider,request_model,prompt,args.timeout,args.ollama_host,args.base_url)
            stem=f"{task}__{label}"; (out/f"{stem}.json").write_text(json.dumps({**r,"task":task,"label":label,"model":model,"request_model":request_model},indent=2)); (out/f"{stem}.out.md").write_text(r["stdout"])
            manifest["results"].append({"task":task,"label":label,"model":model,"request_model":request_model,"returncode":r["returncode"],"elapsed_s":r["elapsed_s"],"stdout_path":f"{stem}.out.md"})
            print(f"DONE {task} {label} rc={r['returncode']} elapsed={r['elapsed_s']}",flush=True)
    (out/"manifest.json").write_text(json.dumps(manifest,indent=2)); print(out)
if __name__=="__main__": main()
