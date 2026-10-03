"""Unified-memory (amdgpu) placement evidence for a prospective comparison.

The nvidia-smi validators do not apply to the Z13's iGPU. Here the serving process
tree's own DRM clients (/proc/<pid>/fdinfo, amdgpu drm-memory-vram/gtt) are
attributed, and everything else on the GPU is "foreign". UMA GTT is not discrete
GPU spill; a low attributed share is labelled mixed, not refused. Host memory
pressure, swap, AC state and platform profile are recorded with every snapshot.
Bracketing snapshots only: not continuous telemetry or proof of zero CPU work.
"""
from __future__ import annotations

from comparison_preflight import PreflightError, require

UMA_KIND = "uma-amdgpu"

# argv: port nonce [gguf_path]. Read-only; hashes the GGUF when a path is given.
UMA_CAPTURE = r'''
import glob,hashlib,json,os,re,subprocess,sys,urllib.request
port=int(sys.argv[1]); nonce=sys.argv[2]; path=sys.argv[3] if len(sys.argv)>3 else None
def run(args): return subprocess.check_output(args,text=True,timeout=15)
listeners=run(['ss','-ltnp',f'sport = :{port}'])
pids=sorted(set(int(p) for p in re.findall(r'pid=(\d+)',listeners)))
if len(pids)!=1: raise RuntimeError('expected one visible serving listener PID')
processes=[dict(zip(('pid','ppid'),map(int,line.split()))) for line in run(['ps','-eo','pid=,ppid=']).splitlines()]
clients={}
for fd in glob.glob('/proc/[0-9]*/fdinfo/*'):
    try: text=open(fd).read()
    except OSError: continue
    if 'drm-driver:\tamdgpu' not in text: continue
    f=dict(re.findall(r'^([\w-]+):\s+(.*)$',text,re.M))
    cid=f.get('drm-client-id')
    if cid is None or cid in clients: continue
    kib=lambda k:int(f.get(k,'0 KiB').split()[0])
    clients[cid]={'pid':int(fd.split('/')[2]),'vram_kib':kib('drm-memory-vram'),'gtt_kib':kib('drm-memory-gtt')}
dev=glob.glob('/sys/class/drm/card*/device/mem_info_gtt_used')[0].rsplit('/',1)[0]
g=lambda n:int(open(f'{dev}/{n}').read())
meminfo={l.split(':')[0]:int(l.split()[1]) for l in open('/proc/meminfo') if l.startswith(('MemTotal','MemAvailable','SwapTotal','SwapFree'))}
ac=[open(p).read().strip() for p in glob.glob('/sys/class/power_supply/*/online')]
out={'nonce':nonce,'host':run(['hostname']).strip(),'port':port,'listener_pid':pids[0],'processes':processes,
     'drm_clients':list(clients.values()),
     'gpu':{'vram_used':g('mem_info_vram_used'),'vram_total':g('mem_info_vram_total'),'gtt_used':g('mem_info_gtt_used'),'gtt_total':g('mem_info_gtt_total')},
     'meminfo_kib':meminfo,'ac_online':ac,'platform_profile':open('/sys/firmware/acpi/platform_profile').read().strip()}
try: out['api_ps']=json.load(urllib.request.urlopen(f'http://127.0.0.1:{port}/api/ps',timeout=5))
except Exception: pass
if path:
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda: f.read(1<<24), b''): h.update(b)
    out['gguf']={'path':path,'sha256':h.hexdigest(),'bytes':os.path.getsize(path)}
print(json.dumps(out))
'''


def model_bytes(contract: dict, tag: str) -> int:
    model = contract["models"][tag]
    value = model.get("gguf_bytes", model.get("weight_bytes"))
    require(type(value) is int and value > 0, f"{tag}: declare gguf_bytes or weight_bytes")
    return value


def validate_uma_placement(contract: dict, tag: str, remote: dict, local_ps: dict | None = None) -> dict:
    expected = contract.get("placement", {})
    require(expected.get("kind") == UMA_KIND, "not a unified-memory placement contract")
    require(remote.get("host") == expected.get("host") and bool(expected.get("host")), "remote host mismatch")
    require(remote.get("port") == expected.get("port") and type(expected.get("port")) is int, "remote listener port mismatch")
    daemon = remote.get("listener_pid")
    require(type(daemon) is int and daemon > 0, "no attributed remote listener")
    require("1" in remote.get("ac_online", []), "not on AC power")
    profile = expected.get("platform_profile")
    require(isinstance(profile, str) and remote.get("platform_profile") == profile,
            f"platform profile {remote.get('platform_profile')!r}, contract declares {profile!r}")
    parents = {int(p["pid"]): int(p["ppid"]) for p in remote.get("processes", [])}
    owned = {daemon}
    while True:
        more = {pid for pid, ppid in parents.items() if ppid in owned}
        if more <= owned:
            break
        owned |= more
    mine = [c for c in remote.get("drm_clients", []) if c["pid"] in owned]
    attributed_mib = sum(c["vram_kib"] + c["gtt_kib"] for c in mine) / 1024
    require(attributed_mib > 0, "no GPU memory attributed to the serving process tree")
    gpu = remote["gpu"]
    used_mib = (gpu["vram_used"] + gpu["gtt_used"]) / 2**20
    foreign_mib = max(0.0, used_mib - attributed_mib)
    ceiling = expected.get("maximum_foreign_mib")
    require(type(ceiling) in (int, float) and ceiling >= 0, "declare maximum_foreign_mib")
    require(foreign_mib <= ceiling, f"foreign GPU memory {foreign_mib:.0f} MiB above {ceiling}; do not evict it")
    share = attributed_mib * 2**20 / model_bytes(contract, tag)
    minimum = contract["models"][tag].get("placement", {}).get("minimum_weight_allocation_ratio")
    if minimum is not None:
        require(share >= minimum, f"attributed allocation below declared bound: {share:.3f} < {minimum}")
    result = {"proved": True, "kind": UMA_KIND, "host": remote["host"], "listener_pid": daemon,
              "attributed_mib": round(attributed_mib, 1),
              "attributed_vram_mib": round(sum(c["vram_kib"] for c in mine) / 1024, 1),
              "attributed_gtt_mib": round(sum(c["gtt_kib"] for c in mine) / 1024, 1),
              "foreign_mib": round(foreign_mib, 1), "weight_allocation_ratio": round(share, 4),
              "label": "gpu-resident" if share >= 0.9 else "mixed",
              "mem_available_mib": remote["meminfo_kib"]["MemAvailable"] // 1024,
              "swap_used_mib": (remote["meminfo_kib"]["SwapTotal"] - remote["meminfo_kib"]["SwapFree"]) // 1024,
              "platform_profile": remote["platform_profile"], "zero_cpu_offload_proved": False}
    if local_ps is not None:
        loaded = remote.get("api_ps", {}).get("models", [])
        local = local_ps.get("models", [])
        require(len(local) == len(loaded) == 1, "require exactly one loaded model on the study daemon")
        for rows in (local, loaded):
            require(rows[0].get("name") == tag and rows[0].get("digest") == contract["models"][tag]["digest"],
                    "tunnel/remote loaded model identity mismatch")
        require(local[0].get("size_vram") == loaded[0].get("size_vram"), "tunnel and remote placement disagree")
        result["ollama_size_vram_ratio"] = round(loaded[0]["size_vram"] / loaded[0]["size"], 4)
    return result
