#!/usr/bin/env python3
"""Repeatable hardware characterisation standard for the local lane.

WHY THIS EXISTS
---------------
Across 2026-09-05..07 this program produced seven measurements that had to be
retracted. Every one had the same shape: a number was recorded without first
confirming the thing being measured had actually happened. Undispatched trials
scored as failures, VRAM sampled before eviction completed, a layer count read
from a vision projector, ledger bookkeeping inside a wall-clock timer, models
that loaded and were evicted before the sample.

This script exists so that hardware claims are made the same way twice. It is
FAIL-CLOSED: every load is verified three ways (the API reports done, the model
is present in `ollama ps`, and VRAM actually moved) before any row is recorded.
A configuration that cannot be verified is reported as FAILED, never as a number.

USAGE
    hw_standard.py --models qwen3.8:27b --ctx 16384 65536
    hw_standard.py --models qwen3.8:27b --ctx 16384 --solo-host 127.0.0.1:11435

    A solo host is a second ollama daemon pinned to one GPU:
        sudo -u ollama env CUDA_VISIBLE_DEVICES=0 OLLAMA_LLM_LIBRARY=cuda_v13 \
             OLLAMA_HOST=127.0.0.1:11435 ollama serve

    OLLAMA_LLM_LIBRARY is REQUIRED, not optional. CUDA_VISIBLE_DEVICES hides a
    card from CUDA but NOT from Vulkan: without it the daemon enumerates
    Vulkan0 = the OTHER card and can allocate on it, so "solo" silently stops
    meaning one card. Observed 2026-09-08 -- a solo daemon listed
    library=Vulkan pci_id=0000:03:00.0 alongside library=CUDA
    pci_id=0000:01:00.0, and one configuration died on "failed to allocate
    Vulkan0 buffer".
    It shares the system model store, so no re-pull is needed.

PROTOCOL (fixed -- do not vary these between runs or the numbers are not comparable)
    prompt         bench_corpora/ctx_code_15k.txt, repeated to reach a target depth
    num_predict    128
    temperature    0            (decode-rate measurement, not a capability trial)
    warmup         one discarded generate per configuration
    reps           3 measured, reported as median with min-max
"""
from __future__ import annotations
import argparse, json, os, pathlib, re, statistics, subprocess, sys, tempfile, time

CORPUS = pathlib.Path.home()/"Python/project-phoenix/docs/bench_corpora/ctx_code_15k.txt"
NUM_PREDICT, TEMPERATURE, REPS = 128, 0, 3
VRAM_LOADED_MIB = 2000          # a real load moves at least this much

def sh(*a, **k): return subprocess.run(a, capture_output=True, text=True, **k)

def ocli(host, *args):
    """Run the ollama CLI against a SPECIFIC daemon.

    Fixed 2026-09-08: evict() and the ps check previously used a bare `ollama`,
    which always talks to :11434 regardless of which daemon is under test. When
    measuring a solo daemon on :11435 that checked the wrong process entirely --
    it saw an empty `ps`, reported "model absent from ollama ps", then looped on
    "GPU not idle" because the solo daemon's model was resident and invisible to
    it. All six solo rows of the first pre-swap run failed this way.
    """
    return subprocess.run(["ollama", *args], capture_output=True, text=True,
                          env={**os.environ, "OLLAMA_HOST": host})

def gpu_rows():
    r = sh("nvidia-smi","--query-gpu=index,memory.used","--format=csv,noheader,nounits")
    return [int(l.split(",")[1]) for l in r.stdout.strip().splitlines() if l.strip()]

def provenance():
    def q(f): return sh("nvidia-smi",f"--query-gpu={f}","--format=csv,noheader").stdout.strip().splitlines()
    cards=[]
    for i,(uuid,bus,name) in enumerate(zip(q("uuid"),q("pci.bus_id"),q("name"))):
        short=bus.strip().replace("00000000:","").rstrip(".0")
        sub=sh("bash","-c",f"lspci -v -s {short} 2>/dev/null | grep -i Subsystem | head -1").stdout
        vendor=sub.split(":")[-1].strip().split(" Device")[0] if ":" in sub else "?"
        lw=sh("bash","-c",f"cat /sys/bus/pci/devices/{bus.strip().lower()}/current_link_width 2>/dev/null").stdout.strip()
        cards.append({"index":i,"name":name.strip(),"vendor":vendor,"pci":bus.strip(),
                      "link_width":f"x{lw}" if lw else "?","uuid":uuid.strip()})
    return {"host":sh("hostname").stdout.strip(),
            "cards":cards,
            "driver":sh("bash","-c","nvidia-smi --query-gpu=driver_version --format=csv,noheader|head -1").stdout.strip(),
            "ollama":sh("ollama","--version").stdout.strip(),
            "protocol":{"num_predict":NUM_PREDICT,"temperature":TEMPERATURE,"reps":REPS,
                        "corpus":str(CORPUS),"warmup":"1 discarded generate"}}

def evict(host, tags):
    """Evict on BOTH daemons -- they share the same physical GPUs, so a model
    resident on the other one still occupies the memory under test."""
    hosts={host, "127.0.0.1:11434"}
    for _ in range(30):
        live=[]
        for h in hosts:
            live += [(h,l.split()[0]) for l in ocli(h,"ps").stdout.splitlines()[1:] if l.strip()]
        if not live and sum(gpu_rows()) < 1500: return True
        for h,m in live: ocli(h,"stop",m)
        time.sleep(3)
    return False

_NONCE=[0]
def generate(host, tag, prompt, uncached=True):
    """One measured generate.

    `uncached` prepends a unique nonce so ollama's prompt cache MISSES. Without
    it every rep after the warmup re-serves a cached prompt and prompt_eval
    time reads ~0.2 s instead of the real cost -- caught 2026-09-08 on this
    script's own first row, where a 12,811-token prompt reported 0.2 s against
    a known ~11.6 s. Prompt processing is the dominant cost at depth, so
    measuring the cache instead of the work would invert the conclusion.
    """
    if uncached:
        _NONCE[0]+=1
        prompt=f"[run {_NONCE[0]} {time.time_ns()}]\n"+prompt
    fd,p = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd,"w") as f:
        json.dump({"model":tag,"prompt":prompt,"stream":False,"keep_alive":"5m",
                   "options":{"num_predict":NUM_PREDICT,"temperature":TEMPERATURE}}, f)
    r = sh("curl","-s","-m","2400",f"http://{host}/api/generate","-d",f"@{p}",timeout=2500)
    os.unlink(p)
    try: d=json.loads(r.stdout)
    except Exception: return {"err":(r.stdout or r.stderr or "no response")[:120]}
    if "error" in d: return {"err":str(d["error"])[:120]}
    g=lambda k:(d.get(k) or 0)/1e9
    return {"load_s":g("load_duration"),"prompt_tok":d.get("prompt_eval_count"),
            "prompt_s":g("prompt_eval_duration"),"eval_tok":d.get("eval_count"),
            "eval_s":g("eval_duration"),"total_s":g("total_duration")}

def layers(since):
    """Layer split from the systemd journal.

    ONLY valid for the system daemon on :11434. A solo daemon started by hand
    (`sudo -u ollama ... nohup ollama serve`) is not under the `ollama` unit, so
    this returns None for it -- which is why every solo row before 2026-09-08
    recorded `layers: None` while a config with a fifth of the model on CPU
    still reported status ok. Use placement() for the authoritative signal.
    """
    out=sh("journalctl","-u","ollama","--since",since,"--no-pager").stdout
    found=re.findall(r"offloaded (\d+)/(\d+) layers", out)
    if not found: return None
    a,b=max(found,key=lambda t:int(t[1]))      # the LLM, not a vision projector
    return f"{a}/{b}"

def placement(host, tag):
    """GPU-resident fraction from /api/ps on the daemon actually under test.

    Added 2026-09-08. Daemon-agnostic, needs no journal access and no assumption
    about which unit the daemon runs under. `size_vram < size` means part of the
    model is on CPU. Must be called while the model is still loaded, before evict.
    """
    r=sh("curl","-s","-m","5",f"http://{host}/api/ps")
    try: d=json.loads(r.stdout or "{}")
    except Exception: return {"placement_err":"unparseable /api/ps"}
    stem=tag.split(":")[0]
    for m in d.get("models") or []:
        if str(m.get("name","")).startswith(stem):
            size=m.get("size") or 0
            vram=m.get("size_vram") or 0
            return {"size_bytes":size,"size_vram_bytes":vram,
                    "gpu_frac":round(vram/size,4) if size else None,
                    "fully_resident":bool(size) and vram>=size}
    return {"placement_err":f"{stem} not in /api/ps on {host}"}

def measure(host, base, ctx, depth_mult, label):
    tag=f"hwstd-{ctx}-{base.split(':')[0].replace('.','')}:latest"
    open("/tmp/hwstd.Modelfile","w").write(f"FROM {base}\nPARAMETER num_ctx {ctx}\n")
    if ocli(host,"create",tag,"-f","/tmp/hwstd.Modelfile").returncode:
        return {"config":label,"status":"FAILED","why":"ollama create failed"}
    if not evict(host,[tag]):
        return {"config":label,"status":"FAILED","why":"could not reach a clean idle GPU state "
                "(another workload is resident -- pause it and re-run)"}
    idle=gpu_rows()
    since=sh("date","+%Y-%m-%d %H:%M:%S").stdout.strip()
    prompt=CORPUS.read_text()*depth_mult
    first=generate(host,tag,prompt)                       # warmup, discarded
    if "err" in first:
        sh("ollama","rm",tag)
        return {"config":label,"status":"FAILED","why":first["err"]}
    time.sleep(3); v=gpu_rows()
    net=[max(0,v[i]-idle[i]) for i in range(len(v))]
    ps=[l for l in ocli(host,"ps").stdout.splitlines()[1:] if l.strip()]
    # THREE independent confirmations that a load really happened
    if not ps:                       return _fail(tag,label,"model absent from `ollama ps` after generate")
    if sum(net) < VRAM_LOADED_MIB:   return _fail(tag,label,f"VRAM moved only {sum(net)} MiB; no real load")
    reps=[generate(host,tag,prompt) for _ in range(REPS)]
    if any("err" in r for r in reps): return _fail(tag,label,"a measured rep failed")
    dec=[r["eval_tok"]/r["eval_s"] for r in reps if r["eval_s"]]
    pro=[r["prompt_s"] for r in reps]
    # A large prompt that processes suspiciously fast means the cache was hit.
    if reps[0]["prompt_tok"] and reps[0]["prompt_tok"] > 2000 and statistics.median(pro) < 1.0:
        return _fail(tag,label,f"prompt cache hit: {reps[0]['prompt_tok']} tok in "
                     f"{statistics.median(pro):.2f}s -- nonce failed to defeat caching")
    row={"config":label,"status":"ok","model":base,"num_ctx":ctx,
         "prompt_tok":reps[0]["prompt_tok"],
         "load_s":round(first["load_s"],1),
         "warmup_prompt_s":round(first["prompt_s"],1),
         "prompt_s_median":round(statistics.median(pro),1),
         "decode_tok_s_median":round(statistics.median(dec),1),
         "decode_min":round(min(dec),1),"decode_max":round(max(dec),1),
         "vram_mib_per_card":net,"vram_mib_total":sum(net),
         "cards_used":sum(1 for x in net if x>VRAM_LOADED_MIB),
         "layers":layers(since),
         **placement(host,tag)}
    ocli(host,"stop",tag); ocli(host,"rm",tag)
    return row

def _fail(tag,label,why,host="127.0.0.1:11434"):
    ocli(host,"stop",tag); ocli(host,"rm",tag)
    return {"config":label,"status":"FAILED","why":why}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--models",nargs="+",required=True)
    ap.add_argument("--ctx",nargs="+",type=int,default=[16384])
    ap.add_argument("--depth-mult",nargs="+",type=int,default=[1],
                    help="corpus repeats; 1 is ~12.8k prompt tokens")
    ap.add_argument("--host",default="127.0.0.1:11434")
    ap.add_argument("--solo-host",default=None,help="second daemon pinned to one GPU")
    ap.add_argument("--out",default=None)
    a=ap.parse_args()
    if not CORPUS.is_file(): sys.exit(f"corpus missing: {CORPUS}")
    rec={"provenance":provenance(),"rows":[]}
    targets=[("dual",a.host)]+([("solo",a.solo_host)] if a.solo_host else [])
    for label,host in targets:
        for m in a.models:
            for ctx in a.ctx:
                for mult in a.depth_mult:
                    lab=f"{label}|{m}|ctx{ctx}|x{mult}"
                    print(f"  measuring {lab} ...",flush=True)
                    row=measure(host,m,ctx,mult,lab); rec["rows"].append(row)
                    print(f"    {json.dumps(row)}",flush=True)
    out=a.out or f"hw_standard_{rec['provenance']['host']}_{time.strftime('%Y%m%d-%H%M')}.json"
    pathlib.Path(out).write_text(json.dumps(rec,indent=2))
    bad=[r for r in rec["rows"] if r["status"]!="ok"]
    print(f"\nwrote {out}  ({len(rec['rows'])-len(bad)} ok, {len(bad)} failed)")
    for r in bad: print(f"  FAILED {r['config']}: {r['why']}")
    sys.exit(1 if bad else 0)

if __name__=="__main__": main()
