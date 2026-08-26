#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,re
from pathlib import Path
CHECKS={
"ppr1_product_boundary":[("four_surfaces",[r"Registry tools.*CLI.*Charter.*Analyst Desk|four surfaces|4 surfaces"]),("fifteen_tools",[r"15 .*tools|fifteen .*tools"]),("full_count",[r"3,?576"]),("published_count",[r"1,?483"]),("published_pct",[r"41\.5"]),("not_clinical",[r"not clinical|not.*monitoring|not.*programming"]),("offline_pdf",[r"offline.*PDF|PDF.*offline"]),("not_chatbot",[r"not.*chatbot|deterministic.*not.*chatbot|not.*LLM"]),("extract_boundary",[r"extract|not.*Phoenix|not.*full.*system"])],
"ppr2_gate_query_semantics":[("rul001",[r"PPR-RUL-001|RUL-001|precedence"]),("rul002",[r"PPR-RUL-002|RUL-002|normalization"]),("rul003",[r"PPR-RUL-003|RUL-003|year.*cap"]),("mdt2030",[r"mdt 2030|2030.*2025|MDT.*2025"]),("stjude2007",[r"st jude 2007|2007.*2008|company.*null"]),("allowed_not_reject",[r"allowed.*true|does not hard|not hard.*deny|not reject"]),("query_vs_gate",[r"query.*execute|gate.*policy|does not execute"]),("missing_fail_closed",[r"missing.*fail.*closed|fail.*closed"]),("partial_visible",[r"partial.*charter|fallback"])] ,
"ppr3_real_data_report":[("mdt_icd",[r"MDT.*23.*60.*918,?205|918,?205.*MDT"]),("abt_icd",[r"ABT.*10.*32.*423,?440|423,?440.*ABT"]),("top_azure",[r"Azure XT DR.*623,?926|623,?926.*Azure"]),("top_adapta",[r"Adapta DR.*454,?869|454,?869.*Adapta"]),("top_abt_pm",[r"PM2272|383,?089"]),("top_bsx",[r"278,?000|ACCOLADE|PROPONENT|ESSENTIO"]),("hhi",[r"3912\.31"]),("high",[r"High"]),("shares",[r"52\.96.*24\.42.*22\.61|MDT.*52\.96|ABT.*24\.42|BSX.*22\.61"]),("historical",[r"historical|not clinical|not.*advice"])]}
def ok(t,ps): return any(re.search(p,t,re.I|re.S) for p in ps)
def main():
 ap=argparse.ArgumentParser(); ap.add_argument("run_dir",type=Path); a=ap.parse_args(); m=json.loads((a.run_dir/"manifest.json").read_text()); rows=[]; totals={}
 for it in m["results"]:
  txt=(a.run_dir/it["stdout_path"]).read_text(errors="replace"); checks={n:ok(txt,ps) for n,ps in CHECKS[it["task"]]}; score=sum(checks.values()); maxs=len(checks); rows.append({**it,"score":score,"max_score":maxs,"checks":checks}); totals.setdefault(it["label"],{"score":0,"max_score":0,"elapsed_s":0}); totals[it["label"]]["score"]+=score; totals[it["label"]]["max_score"]+=maxs; totals[it["label"]]["elapsed_s"]+=it["elapsed_s"]
 report={"run_dir":str(a.run_dir),"rows":rows,"totals":totals}; (a.run_dir/"scores.json").write_text(json.dumps(report,indent=2))
 print("# PPR Agent benchmark scores\n\n| model | task | score | elapsed_s |\n|---|---|---:|---:|")
 for r in rows: print(f"| {r['label']} | {r['task']} | {r['score']}/{r['max_score']} | {r['elapsed_s']} |")
 print("\n| model | total | elapsed_s |\n|---|---:|---:|")
 for label,t in sorted(totals.items(),key=lambda kv:(-kv[1]['score'],kv[1]['elapsed_s'])): print(f"| {label} | {int(t['score'])}/{int(t['max_score'])} | {round(t['elapsed_s'],3)} |")
if __name__=="__main__": main()
