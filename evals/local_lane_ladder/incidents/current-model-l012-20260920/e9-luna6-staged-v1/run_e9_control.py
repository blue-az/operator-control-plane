#!/usr/bin/env python3
import json,os,subprocess,tempfile,time
from pathlib import Path
from adapter import contract,execute_deterministic,grade,redact,TASKS
from carrier_wrapper import parse_plan
from carrier_wrapper import planner_prompt
PKG=Path(__file__).parent; MODEL=os.environ.get('E9_MODEL','gpt-6-luna'); stamp=os.environ['E9_RUN_STAMP']; mode=os.environ.get('E9_MODE','screen'); level=os.environ.get('E9_LEVEL','L2'); root=PKG/'runs'/f'e9-luna6-{mode}-{stamp}'; root.mkdir(parents=True,exist_ok=False)
(root/'alias-identity.txt').write_text(f"{MODEL} via codex exec\\n"); (root/'cli-version.txt').write_text(subprocess.run(['codex','--version'],text=True,capture_output=True).stdout.strip()+"\n"); (root/'policy.txt').write_text('v1 E9 staged control; planner contract failures are failed cells; no retry; deterministic adapter-owned grading. Carrier: codex exec, sandbox read-only, approval_policy never. NOT carrier-equivalent to the Haiku control, which ran claude -p with --tools \'\' and no read access: these are separate observations and are never pooled.\n')
def call(prompt,fixture):
 t=time.monotonic()
 out=tempfile.NamedTemporaryFile('w+',suffix='.txt',delete=False); out.close()
 # read-only sandbox + approvals never: the planner is meant to emit a plan, not
 # act, and the executor is adapter-owned. workspace-write with this account's
 # approval_mode=approve blocks on a prompt nobody answers -- the first screen
 # cell timed out at 300s that way. Asymmetry against the Haiku control, which
 # ran with --tools '' and could not read at all, is recorded in policy.txt.
 a=['codex','exec','--model',MODEL,'--skip-git-repo-check','--sandbox','read-only',
    '-c','approval_policy="never"','--output-last-message',out.name,'--cd',str(fixture),prompt]
 p=subprocess.run(a,text=True,capture_output=True,timeout=300)
 body=Path(out.name).read_text() if Path(out.name).exists() else ''
 Path(out.name).unlink(missing_ok=True)
 # Fall back to stdout only when the last-message file is empty, so a transport
 # change shows up as a contract failure rather than silently grading chrome.
 return redact(a),p.returncode,redact(body or p.stdout),redact(p.stderr),round(time.monotonic()-t,3)

def one(idx,task,trial):
 c=contract(task,level); d=root/'cells'/f'{idx:03d}-{task}-{level}-t{trial}'; f=d/'fixture'; f.mkdir(parents=True)
 for k,v in c['files'].items(): q=f/k;q.parent.mkdir(parents=True,exist_ok=True);q.write_text(v)
 (d/'fixture-pre.json').write_text(json.dumps(c['files'],sort_keys=True)+'\n')
 row={'cell':c,'trial':trial,'task':task}
 try:
  a,rc,out,err,tm=call(planner_prompt(c),f); row.update(planner_argv=a,planner_exit_status=rc,planner_raw=out,planner_stderr=err,planner_wall_clock_s=tm)
  if rc: raise RuntimeError('planner CLI exit')
  steps=parse_plan(out,c); row['trajectory']=redact(steps); t=time.monotonic(); ev=execute_deterministic(c,steps,f); row['executor_wall_clock_s']=round(time.monotonic()-t,3);row['compact_evidence']=redact(ev)
  a,rc,out,err,tm=call('Return concise grounded final answer from this compact evidence only: '+json.dumps(redact(ev)),f); row.update(synthesis_argv=a,synthesis_exit_status=rc,synthesis_raw=out,synthesis_stderr=err,synthesis_wall_clock_s=tm,grade=grade(c,ev,out),classification='valid')
  (d/'fixture-post.json').write_text(json.dumps({'files':ev['workspace_files']},sort_keys=True)+'\n')
 except Exception as e: row.update(classification='planner_contract_failure' if isinstance(e,ValueError) else 'invalid',stop_reason=type(e).__name__+': '+str(e))
 (d/'cell.json').write_text(json.dumps(row,sort_keys=True,indent=2)+'\n'); return row
if mode=='screen': cells=[('ambiguous-anchor',1)]
elif mode=='calibration': cells=[(t,tr) for tr in range(1,5) for t in ('constant-and-callers','csv-summarize-repair')]
else: cells=[(t,tr) for tr in range(1,7) for t in TASKS]
rows=[one(i,t,tr) for i,(t,tr) in enumerate(cells,1)]; (root/'RESULTS.json').write_text(json.dumps(rows,sort_keys=True,indent=2)+'\n'); print(json.dumps({'root':str(root),'mode':mode,'rows':len(rows),'passed':sum(r.get('grade',{}).get('passed',False) for r in rows)},sort_keys=True))
