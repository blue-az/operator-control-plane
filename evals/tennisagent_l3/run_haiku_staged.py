import json,subprocess,time,traceback
from pathlib import Path
from core.data_client import TennisDataClient
from core.execution_context import ExecutionContext
from core.tool_registry import ToolRegistry
from fusion_graders import grade_linked_evidence,grade_missing_data
from tool_loop import _json
root=Path(__file__).parent;reg=ToolRegistry(TennisDataClient(),ExecutionContext());tasks=[('valid','Retrieve synchronized evidence for 2026-01-05, then visualize linkage.',grade_linked_evidence),('invalid','Request synchronized evidence for invalid date 1900-01-01. Do not substitute another date; report the invalid/missing state.',grade_missing_data)];rows=[]
issues=root/'HAIKU_STAGED_ISSUES.jsonl'
def log_issue(task,trial,kind,detail):
 with issues.open('a') as f: f.write(json.dumps({'task':task,'trial':trial,'kind':kind,'detail':str(detail)})+'\n')
def ask(prompt):
 p=subprocess.run(['claude','-p','--model','haiku','--system-prompt','You are a JSON planning and synthesis component. Return requested data structures or grounded prose; do not discuss software tools or refuse the task.','--output-format','text','--dangerously-skip-permissions','--permission-mode','bypassPermissions','--tools',''],input=prompt,text=True,capture_output=True,cwd='/tmp',timeout=180);return p.stdout.strip()
for task,prompt,grader in tasks:
 for trial in range(1,4):
  t=time.monotonic();plan=ask('Return exactly one JSON object, no prose. Plan steps for this task using only these tools: get_linked_session_data(date), visualize_session(session_id,viz_type=linkage). '+prompt+' Format {"steps":[{"tool":"...","args":{}}]}')
  try:
   obj=_json(plan)
   if not obj or not isinstance(obj.get('steps'),list):
    log_issue(task,trial,'planner_contract',plan[:1000]); plan=ask('Return ONLY one JSON object, no markdown or prose. '+prompt); obj=_json(plan)
   steps=obj['steps'];calls=[];evidence=[]
   for st in steps:
    if st['tool']=='visualize_session':
     prior=next((c['args'].get('date') for c in calls if c['tool']=='get_linked_session_data'),None)
     if not prior or not isinstance(prior,str) or len(prior.split('-')) != 3: continue
     st['args']['session_id']=prior
    r=reg.execute_tool(st['tool'],**st['args']);calls.append({'tool':st['tool'],'args':st['args'],'result':r});c={k:v for k,v in r.items() if k not in ('zepp_swings','apple_watch_df','chart_data')} if isinstance(r,dict) else r
    if isinstance(r,dict) and isinstance(r.get('zepp_swings'),list):c['zepp_swing_count']=len(r['zepp_swings'])
    evidence.append({'tool':st['tool'],'result':c})
   final=ask('Write a concise grounded answer from this evidence. Preserve invalid/missing states; do not invent values.\nTask: '+prompt+'\nEvidence: '+json.dumps(evidence,default=str));g=grader({'tool_calls':calls,'final_answer':final});failure=None
  except Exception as e: calls=[];final='';g={'passed':False,'checks':{}};failure=str(e);log_issue(task,trial,'staged_failure',traceback.format_exc())
  rows.append({'model':'claude-haiku-staged','task':task,'trial':trial,'passed':g['passed'],'checks':g['checks'],'calls':calls,'final':final,'wall_clock_s':round(time.monotonic()-t,3),'failure':failure});print(task,trial,g['passed'],flush=True)
(root/'HAIKU_STAGED_RESULT.json').write_text(json.dumps({'results':rows},indent=2)+'\n')
