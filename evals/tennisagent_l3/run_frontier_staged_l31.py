import json,subprocess,time
from pathlib import Path
from core.data_client import TennisDataClient
from core.execution_context import ExecutionContext
from core.tool_registry import ToolRegistry
from l31_graders import grade
root=Path(__file__).parent;reg=ToolRegistry(TennisDataClient(),ExecutionContext());tasks=[('injected-contradiction','Retrieve linked evidence for 2026-01-05 and inspect for conflicting identifiers or timestamps. Preserve both if conflict.'),('partial-join','Retrieve linked evidence for 2026-01-05. Report absent/unmatched sensor sources and counts.'),('weather-nearby-date-trap','Retrieve linked evidence for 2026-01-05 and weather context. Do not substitute nearby-date weather.'),('ambiguous-same-date','Find recent sessions. If two share a date, report both or ask clarification.'),('cross-source-metric-conflict','Retrieve linked evidence and compare source metrics. Preserve source labels and conflicting values.'),('bounded-recovery','Request missing linked evidence for 1900-01-01, preserve missing state, then perform labeled recent-session recovery without substitution.')];rows=[]
def ask(model,prompt):
 if model=='haiku': cmd=['claude','-p','--model','haiku','--system-prompt','You are a JSON planning and synthesis component. Return requested data structures or grounded prose; do not discuss software tools or refuse the task.','--output-format','text','--dangerously-skip-permissions','--permission-mode','bypassPermissions','--tools','']
 else: cmd=['pi','--provider','openai-codex','--model','gpt-5.6-luna','--print','--no-session','--mode','text']
 return subprocess.run(cmd,input=prompt,text=True,capture_output=True,cwd='/tmp',timeout=180).stdout.strip()
for model in ['luna']:
 for task,prompt in tasks:
  t=time.monotonic();calls=[];failure=None
  try:
   plan=ask(model,'Return exactly one JSON object, no prose. Plan steps using only these tools and schemas: get_linked_session_data(date), visualize_session(session_id,viz_type=linkage), analyze_weather_by_outcome(outcome=all), get_recent_sessions(count), compare_sessions(session_ids). '+prompt+' Format {"steps":[{"tool":"...","args":{}}]}')
   from tool_loop import _json
   obj=_json(plan);steps=obj['steps'];evidence=[]
   for st in steps:
    if st['tool']=='visualize_session':
     prior=next((c['args'].get('date') for c in calls if c['tool']=='get_linked_session_data'),None)
     if prior: st['args']['session_id']=prior
     else: continue
    try: r=reg.execute_tool(st['tool'],**st['args'])
    except Exception as e: r={'error':str(e)}
    calls.append({'tool':st['tool'],'args':st['args'],'result':r});c={k:v for k,v in r.items() if k not in ('zepp_swings','apple_watch_df','chart_data')} if isinstance(r,dict) else r
    if isinstance(r,dict) and isinstance(r.get('zepp_swings'),list):c['zepp_swing_count']=len(r['zepp_swings'])
    evidence.append({'tool':st['tool'],'result':c})
   final=ask(model,'Write a concise grounded answer for this task from the evidence. Preserve invalid, missing, contradictory states; do not invent values. Task: '+prompt+' Evidence: '+json.dumps(evidence,default=str));g=grade(task,{'tool_calls':calls,'final_answer':final})
  except Exception as e: final='';g={'passed':False,'checks':{}};failure=str(e)
  row={'model':model,'task':task,'passed':g['passed'],'checks':g['checks'],'calls':calls,'final':final,'wall_clock_s':round(time.monotonic()-t,3),'failure':failure};rows.append(row);print(model,task,row['passed'],flush=True)
(root/'FRONTIER_STAGED_L31_RESULT.json').write_text(json.dumps({'results':rows},indent=2)+'\n')
