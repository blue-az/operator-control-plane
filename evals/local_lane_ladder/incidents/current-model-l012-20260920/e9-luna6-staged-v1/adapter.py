#!/usr/bin/env python3
"""L3-analog Haiku staged carrier; transport callbacks are injected, never called here."""
from __future__ import annotations
import json,re
from pathlib import Path
import yaml
ROOT=Path(__file__).parent; ALIAS='haiku'; CLI_VERSION='2.1.278 (Claude Code)'
TASKS=('ambiguous-anchor','csv-summarize-repair','strict-log-format'); LEVELS=('L2',)
TOOLS={'read_file','write_file','run_check'}; SECRET=re.compile(r'(authorization|api[_-]?key|token|secret|cookie|password)',re.I)
def redact(x):
 if isinstance(x,dict): return {k:('[REDACTED]' if SECRET.search(k) else redact(v)) for k,v in x.items()}
 if isinstance(x,list): return [redact(v) for v in x]
 return x
def fresh_root(parent,stamp):
 p=Path(parent)/f'current-three-haiku-l012-{stamp}'
 if p.exists(): raise FileExistsError(p)
 p.mkdir(parents=True); (p/'RUN_ROOT_DECLARED').write_text(str(p)+'\n'); return p
def contract(task,level):
 d=yaml.safe_load((ROOT/(task.replace('-','_')+'.yaml')).read_text()); return {'task_id':task,'level':level,'prompt':d['prompts'][level],'files':d['files'],'postcondition':d['postcondition']}
def plan(): return [contract(t,l) for t in TASKS for l in LEVELS for _ in range(3)]
def cli_argv(prompt): return ['claude','-p','--model',ALIAS,'--output-format','text','--system-prompt','JSON planner/synthesis only','--permission-mode','bypassPermissions','--tools','',prompt]
def allowed_check(cell):
 return {'grep':'postcondition_grep','exec':'postcondition_exec','output_contains':'postcondition_output_contains'}[cell['postcondition']['type']]

def validate_step(step,cell):
 if not isinstance(step,dict) or step.get('tool') not in TOOLS: raise ValueError('unknown/malformed tool')
 args=step.get('args');
 if not isinstance(args,dict): raise ValueError('malformed args')
 path=args.get('path')
 if step['tool'] in {'read_file','write_file'}:
  if not isinstance(path,str) or path.startswith('/') or '..' in Path(path).parts or path not in cell['files']: raise ValueError('fixture path escape')
 if step['tool']=='run_check' and set(args)!=set(): raise ValueError('run_check takes no planner args')
 return True
def execute_deterministic(cell,steps,fixture):
 fixture=Path(fixture); fixture.mkdir(parents=True,exist_ok=True); state={}
 # Validate the complete trajectory before any mutation; grading is adapter-owned.
 for s in steps: validate_step(s,cell)
 for s in steps:
  a=s['args']; p=fixture/a.get('path','')
  if s['tool']=='read_file': state[a['path']]=p.read_text() if p.exists() else ''
  elif s['tool']=='write_file': p.parent.mkdir(parents=True,exist_ok=True); p.write_text(a.get('content','')); state[a['path']]=a.get('content','')
  else: state['check']=cell['postcondition']
 return {'workspace_files':{k:(fixture/k).read_text() for k in cell['files'] if (fixture/k).exists()},'state':state}
def compact(evidence): return redact(evidence)
def grade(cell,evidence,final_output=''):
 from grading import grade as deterministic_grade
 import tempfile
 with tempfile.TemporaryDirectory() as td:
  root=Path(td)
  for rel,content in evidence.get('workspace_files',{}).items():
   target=root/rel; target.parent.mkdir(parents=True,exist_ok=True); target.write_text(content)
  result=deterministic_grade(cell['postcondition'],root,final_output or evidence.get('final_output',''),manifest=cell['files'])
 return {'passed':result.passed,'classification':'pass' if result.passed else 'fail','detail':result.detail,'checks':[{'name':c.name,'passed':c.passed,'detail':c.detail} for c in result.checks]}
def cell_record(root,cell,planner,synthesis,fixture):
 steps=planner(cell); evidence=execute_deterministic(cell,steps,fixture); final=synthesis(compact(evidence)); return {'cell':cell,'planner':redact(steps),'evidence':compact(evidence),'synthesis':redact(final),'grade':grade(cell,evidence)}
if __name__=='__main__': print(json.dumps({'alias':ALIAS,'cli_version':CLI_VERSION,'cells':len(plan()),'tasks':TASKS,'levels':LEVELS},sort_keys=True))
