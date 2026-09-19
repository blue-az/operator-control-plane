from l31_graders import grade

def test_all():
 cases={
 'injected-contradiction':'Sources conflict; preserve both identifiers.',
 'partial-join':'Zepp absent; unmatched count is 1.',
 'weather-nearby-date-trap':'Weather is unavailable for requested date; do not substitute nearby date.',
 'ambiguous-same-date':'Two sessions share date; ask for clarification.',
 'cross-source-metric-conflict':'Sources disagree; preserve both values and source labels.',
 'bounded-recovery':'Primary state missing; recent recovery is labeled, not substitution.'}
 for k,v in cases.items(): assert grade(k,{'tool_calls':[{'tool':'x'}],'final_answer':v})['passed'],k
