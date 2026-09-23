import json,re

def extract_one(text):
 s=text.strip()
 if s.startswith('```'):
  m=re.fullmatch(r'```(?:json)?\s*(\{.*\})\s*```',s,re.S)
  if not m: raise ValueError('incomplete or mixed fence')
  return json.loads(m.group(1))
 spans=[]
 for i,ch in enumerate(s):
  if ch!='{': continue
  try:
   obj,end=json.JSONDecoder().raw_decode(s[i:]); spans.append((i,i+end,obj))
  except json.JSONDecodeError: pass
 outer=[x for x in spans if not any(y[0] < x[0] and y[1] >= x[1] for y in spans)]
 if len(outer)!=1: raise ValueError(f'expected exactly one JSON object, found {len(outer)}')
 obj=outer[0][2]
 if not isinstance(obj,dict): raise ValueError('JSON object required')
 return obj
