import json,subprocess,time,os,tempfile
def sh(*a,**k): return subprocess.run(a,capture_output=True,text=True,**k)
def ocli(h,*a): return subprocess.run(["ollama",*a],capture_output=True,text=True,
                                      env={**os.environ,"OLLAMA_HOST":h})
H="127.0.0.1:11434"
def gpus():
    r=sh("nvidia-smi","--query-gpu=memory.used","--format=csv,noheader,nounits")
    return [int(x) for x in r.stdout.split() if x.strip().isdigit()]
def evict():
    for _ in range(25):
        live=[]
        for h in (H,"127.0.0.1:11435"):
            live+=[(h,l.split()[0]) for l in ocli(h,"ps").stdout.splitlines()[1:] if l.strip()]
        if not live and sum(gpus())<1500: return True
        for h,m in live: ocli(h,"stop",m)
        time.sleep(3)
    return False
def gen(tag,npred=8,prompt="Reply with exactly one word."):
    fd,p=tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd,"w") as f:
        json.dump({"model":tag,"prompt":prompt,"stream":False,"keep_alive":"15m",
                   "options":{"num_predict":npred,"temperature":0}},f)
    t0=time.time()
    r=sh("curl","-s","-m","1200",f"http://{H}/api/generate","-d",f"@{p}",timeout=1250)
    os.unlink(p)
    d={}
    try: d=json.loads(r.stdout)
    except Exception: pass
    ok='"done":true' in (r.stdout or "")
    dec=(d.get("eval_count") or 0)/((d.get("eval_duration") or 1)/1e9)
    return ok, time.time()-t0, dec
print(f"{'ctx':>7} {'27b MiB':>8} {'35b MiB':>8} {'total':>7} {'both?':>6} {'switch s':>9} {'27b dec':>8} {'35b dec':>8}  processor")
for ctx in (16384, 24576, 32768, 49152):
    tags={}
    for base in ("qwen3.8:27b","qwen3.6:35b"):
        t=f"cor{ctx}-{base.split(':')[0].replace('.','')}:latest"
        open("/tmp/c.Modelfile","w").write(f"FROM {base}\nPARAMETER num_ctx {ctx}\nPARAMETER temperature 0.8\n")
        ocli(H,"create",t,"-f","/tmp/c.Modelfile"); tags[base]=t
    if not evict(): print(f"{ctx:7}  evict failed"); continue
    idle=gpus()
    ok1,_,d1=gen(tags["qwen3.8:27b"]); time.sleep(2); a=gpus()
    m27=sum(a)-sum(idle)
    ok2,_,d2=gen(tags["qwen3.6:35b"]); time.sleep(3); b=gpus()
    m35=sum(b)-sum(a)
    ps=[l for l in ocli(H,"ps").stdout.splitlines()[1:] if l.strip()]
    both = len(ps)==2
    proc=" | ".join(l.split()[3] if len(l.split())>3 else "?" for l in ps)
    _,sw,d1b=gen(tags["qwen3.8:27b"])
    print(f"{ctx:7} {m27:8} {m35:8} {sum(b)-sum(idle):7} {str(both):>6} {sw:9.1f} {d1b:8.1f} {d2:8.1f}  {proc[:34]}")
    for t_ in tags.values(): ocli(H,"stop",t_); ocli(H,"rm",t_)
