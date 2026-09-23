#!/usr/bin/env python3
import json,os,subprocess,tempfile,time
from pathlib import Path
from adapter import contract,execute_deterministic,grade,redact,TASKS
from carrier_wrapper import parse_plan
from carrier_wrapper import planner_prompt, turn_prompt
PKG=Path(__file__).parent; MODEL=os.environ.get('E9_MODEL','haiku'); stamp=os.environ['E9_RUN_STAMP']; mode=os.environ.get('E9_MODE','screen'); level=os.environ.get('E9_LEVEL','L2'); root=PKG/'runs'/f'e9-haiku-loop-{mode}-{stamp}'; root.mkdir(parents=True,exist_ok=False)
(root/'alias-identity.txt').write_text(f"{MODEL} via claude -p (floating alias)\\n"); (root/'cli-version.txt').write_text(subprocess.run(['claude','--version'],text=True,capture_output=True).stdout.strip()+"\n"); (root/'policy.txt').write_text('v2 E9 turn-loop control; planner contract failures are failed cells; no retry; deterministic adapter-owned grading. Carrier: claude -p with --tools \'\' (no tools; the adapter is the only actor). NOT carrier-equivalent to the Luna control, which runs codex exec under a read-only sandbox and can read files: these are separate observations and are never pooled.\n')
def call(prompt,fixture):
 t=time.monotonic()
 a=['claude','-p','--model',MODEL,'--output-format','text','--system-prompt','JSON planner/synthesis only','--permission-mode','bypassPermissions','--tools','',prompt]
 p=subprocess.run(a,input=prompt,text=True,capture_output=True,cwd=fixture,timeout=300)
 return redact(a),p.returncode,redact(p.stdout),redact(p.stderr),round(time.monotonic()-t,3)

MAX_TURNS=int(os.environ.get('E9_MAX_TURNS','10'))

def one(idx,task,trial):
 c=contract(task,level); d=root/'cells'/f'{idx:03d}-{task}-{level}-t{trial}'; f=d/'fixture'; f.mkdir(parents=True)
 for k,v in c['files'].items(): q=f/k;q.parent.mkdir(parents=True,exist_ok=True);q.write_text(v)
 (d/'fixture-pre.json').write_text(json.dumps(c['files'],sort_keys=True)+'\n')
 row={'cell':c,'trial':trial,'task':task,'carrier':'turn-loop-v2','max_turns':MAX_TURNS}
 turns=[]; trajectory=[]; ev=None; observations=[]
 try:
  for turn in range(1,MAX_TURNS+1):
   a,rc,out,err,tm=call(turn_prompt(c,turn,observations,MAX_TURNS),f)
   rec={'turn':turn,'argv':a,'exit_status':rc,'raw':out,'stderr':err,'wall_clock_s':tm}
   # Record the turn BEFORE parsing. Appending afterwards meant a contract
   # failure discarded the exact output that caused it: the cell reported
   # "found 0 JSON objects" while retaining only the previous turn's text.
   turns.append(rec)
   if rc: raise RuntimeError(f'planner CLI exit on turn {turn}')
   if not (out or '').strip():
    # Empty transport response is a carrier fault, not the model failing a
    # contract. Raise something that classifies as invalid, not as a model cell.
    raise RuntimeError(f'empty planner response on turn {turn}')
   steps=parse_plan(out,c)          # same schema and scope validation as v1
   rec['steps']=redact(steps); trajectory.extend(steps)
   t=time.monotonic(); ev=execute_deterministic(c,trajectory,f)
   rec['executor_wall_clock_s']=round(time.monotonic()-t,3)
   # Hand back what the actions produced. This is the whole point of v2: the
   # model stops guessing at file contents it has not been shown.
   observations=observations+[{'turn':turn,'steps':redact(steps),'state':redact(ev.get('state',{}))}]
   rec['observation']=observations[-1]   # rec is already in `turns`; appending again double-counted
   if any(s['tool']=='run_check' for s in steps): rec['ended']='run_check'; break
  else:
   row['turn_cap_reached']=True
  if ev is None: raise RuntimeError('no executable turn')
  row['turns']=turns; row['turn_count']=len(turns); row['trajectory']=redact(trajectory); row['compact_evidence']=redact(ev)
  a,rc,out,err,tm=call('Return concise grounded final answer from this compact evidence only: '+json.dumps(redact(ev)),f)
  row.update(synthesis_argv=a,synthesis_exit_status=rc,synthesis_raw=out,synthesis_stderr=err,synthesis_wall_clock_s=tm,grade=grade(c,ev,out),classification='valid')
  (d/'fixture-post.json').write_text(json.dumps({'files':ev['workspace_files']},sort_keys=True)+'\n')
 except Exception as e:
  row['turns']=turns; row['turn_count']=len(turns)
  row.update(classification='planner_contract_failure' if isinstance(e,ValueError) else 'invalid',stop_reason=type(e).__name__+': '+str(e))
 (d/'cell.json').write_text(json.dumps(row,sort_keys=True,indent=2)+'\n'); return row
if mode=='screen': cells=[('ambiguous-anchor',1)]
elif mode=='calibration': cells=[(t,tr) for tr in range(1,5) for t in ('constant-and-callers','csv-summarize-repair')]
else: cells=[(t,tr) for tr in range(1,7) for t in TASKS]
rows=[one(i,t,tr) for i,(t,tr) in enumerate(cells,1)]; (root/'RESULTS.json').write_text(json.dumps(rows,sort_keys=True,indent=2)+'\n'); print(json.dumps({'root':str(root),'mode':mode,'rows':len(rows),'passed':sum(r.get('grade',{}).get('passed',False) for r in rows)},sort_keys=True))
