"""Schema-driven model/tool loop for TennisAgent L3; never executes invented tools."""
from __future__ import annotations
import json,re,subprocess,time
from pathlib import Path
import sys
sys.path.insert(0,'/home/blueaz/Python/project-phoenix/domains/TennisAgent/cockpit_poc/agent')
from core.data_client import TennisDataClient
from core.execution_context import ExecutionContext
from core.tool_registry import ToolRegistry

TOOLS={
 'get_linked_session_data': {'date':'YYYY-MM-DD'},
 'visualize_session': {'session_id':'session/date','viz_type':'linkage'},
 'analyze_weather_by_outcome': {'outcome':'all|wins|losses'},
}
REQUIRED_ARGS={'get_linked_session_data': {'date'}, 'visualize_session': {'session_id','viz_type'}, 'analyze_weather_by_outcome': set()}
MAX_TRANSCRIPT_CHARS=12000
CALL_TIMEOUT_SECONDS=90

def _json(text):
    text=text.strip().replace('```json','').replace('```','').strip()
    try:
        x=json.loads(text)
        if isinstance(x,dict): return x
    except json.JSONDecodeError: pass
    for start in [m.start() for m in re.finditer(r'\{\s*"(?:tool|final)"', text)]:
        try:
            x, _ = json.JSONDecoder().raw_decode(text[start:])
            if isinstance(x,dict): return x
        except json.JSONDecodeError: pass
    return None

def run(model:str, prompt:str, turns:int=3):
    client=TennisDataClient(); ctx=ExecutionContext(); reg=ToolRegistry(client,ctx); transcript=prompt; calls=[]; raw_outputs=[]; seen=set(); started=time.monotonic()
    protocol='You are producing instructions for an external executor, not calling native tools. Never refuse due tool availability. Output exactly one JSON object: {"tool":"registered_name","args":{...}} or {"final":"..."}.\\nExact schemas: get_linked_session_data requires {"date":"YYYY-MM-DD"}; visualize_session requires {"session_id":"YYYY-MM-DD","viz_type":"linkage"}; analyze_weather_by_outcome accepts {"outcome":"all|wins|losses"}.\\n'
    transcript=protocol+prompt
    for _ in range(turns):
        if model=='haiku': cmd=['claude','-p','--model','haiku','--output-format','text','--dangerously-skip-permissions','--permission-mode','bypassPermissions','--tools','']
        elif model=='opus': cmd=['claude','-p','--model','opus','--output-format','text','--dangerously-skip-permissions','--permission-mode','bypassPermissions','--tools','']
        elif model=='agy120': cmd=['/home/blueaz/.local/bin/agy','--model','gpt-oss-120b-medium','--output-format','text','--dangerously-skip-permissions','--print='+transcript[-16000:]]
        elif model=='agysonnet': cmd=['/home/blueaz/.local/bin/agy','--model','claude-sonnet-4-6','--output-format','text','--dangerously-skip-permissions','--print='+transcript[-16000:]]
        elif model=='agyflash': cmd=['/home/blueaz/.local/bin/agy','--model','gemini-3.8-flash-high','--output-format','text','--dangerously-skip-permissions','--print='+transcript[-16000:]]
        elif model=='luna': cmd=['pi','--provider','openai-codex','--model','gpt-5.6-luna','--print','--no-session','--mode','text']
        elif model=='astra': cmd=['pi','--provider','openai-codex','--model','gpt-6-astra','--print','--no-session','--mode','text']
        else: cmd=['ssh','testbench','/home/ef-tb/.local/bin/ollama','run',model]
        try: p=subprocess.run(cmd,input=None if model in ('agy120','agysonnet','agyflash') else transcript,text=True,capture_output=True,timeout=CALL_TIMEOUT_SECONDS,cwd='/tmp')
        except subprocess.TimeoutExpired: return {'passed':False,'failure':'provider timeout','calls':calls,'raw_outputs':raw_outputs,'wall_clock_s':round(time.monotonic()-started,3)}
        raw=p.stdout.strip(); raw_outputs.append(raw); obj=_json(raw)
        if not obj: return {'passed':False,'failure':'no JSON tool/final message','raw':raw,'calls':calls,'wall_clock_s':round(time.monotonic()-started,3)}
        if obj.get('final') is not None: return {'passed':True,'final_answer':str(obj['final']),'calls':calls,'wall_clock_s':round(time.monotonic()-started,3)}
        tool=obj.get('tool'); args=obj.get('args',{})
        if tool not in TOOLS: return {'passed':False,'failure':f'unsupported tool: {tool}','calls':calls,'raw_outputs':raw_outputs,'wall_clock_s':round(time.monotonic()-started,3)}
        if set(args) != REQUIRED_ARGS[tool]: return {'passed':False,'failure':f'invalid argument schema for {tool}','calls':calls,'raw_outputs':raw_outputs,'wall_clock_s':round(time.monotonic()-started,3)}
        signature=json.dumps({'tool':tool,'args':args},sort_keys=True)
        if signature in seen:
            transcript=protocol+prompt+'\nAll requested tool calls have already completed. Return only JSON {"final":"..."} with the evidence summary.'
            p=subprocess.run(cmd,input=transcript,text=True,capture_output=True,timeout=300); raw=p.stdout.strip(); obj=_json(raw)
            if obj and obj.get('final') is not None: return {'passed':True,'final_answer':str(obj['final']),'calls':calls,'wall_clock_s':round(time.monotonic()-started,3)}
            return {'passed':False,'failure':'repeated tool call without final','calls':calls,'raw':raw,'wall_clock_s':round(time.monotonic()-started,3)}
        seen.add(signature)
        try: result=reg.execute_tool(tool,**args)
        except Exception as exc: return {'passed':False,'failure':f'invalid arguments for {tool}: {exc}','calls':calls,'raw_outputs':raw_outputs,'wall_clock_s':round(time.monotonic()-started,3)}
        calls.append({'tool':tool,'args':args,'result':result})
        compact=result
        if isinstance(result,dict):
            compact={k:v for k,v in result.items() if k not in {'zepp_swings','apple_watch_df','chart_data'}}
            if isinstance(result.get('zepp_swings'),list): compact['zepp_swing_count']=len(result['zepp_swings'])
        transcript=(protocol+prompt+'\nTool call: '+json.dumps({'tool':tool,'args':args})+'\nTool result: '+json.dumps(compact,default=str)+'\nReturn another JSON tool call or {"final":"..."}.')[-MAX_TRANSCRIPT_CHARS:]
    return {'passed':False,'failure':'turn limit','calls':calls,'wall_clock_s':round(time.monotonic()-started,3)}
