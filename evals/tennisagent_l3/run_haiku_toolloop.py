import json,time
from pathlib import Path
from tool_loop import run
from fusion_graders import grade_missing_data,grade_linked_evidence
root=Path(__file__).parent; out=[]
tasks=[('valid','''Use the available TennisAgent tools. Obtain synchronized evidence for date 2026-01-05, then visualize the linkage. Use JSON tool calls only, then return JSON {"final":"..."} citing date and source identifiers.''',grade_linked_evidence),('invalid','''Use the available TennisAgent tools. Request synchronized evidence for invalid date 1900-01-01. Do not substitute another date. Use JSON tool calls only, then return JSON {"final":"..."} explicitly reporting no data or invalid state.''',grade_missing_data)]
for task,prompt,grader in tasks:
 for trial in range(1,4):
  r=run('haiku',prompt,turns=5); trace={'tool_calls':r.get('calls',[]),'final_answer':r.get('final_answer','')};g=grader(trace);row={'model':'claude-haiku','task':task,'trial':trial,'passed':g['passed'],'checks':g['checks'],'wall_clock_s':r['wall_clock_s'],'failure':r.get('failure'),'calls':r.get('calls',[])};out.append(row);print(task,trial,row['passed'],row['wall_clock_s'],flush=True)
(root/'HAIKU_TOOLLOOP_PILOT.json').write_text(json.dumps({'results':out},indent=2,default=str)+'\n')
