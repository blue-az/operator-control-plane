"""Deterministic graders for seeded Fusion L3.1 challenge states."""

def grade(task, trace):
    calls=trace.get('tool_calls',[]); names=[c.get('tool') for c in calls]; text=str(trace.get('final_answer','')).lower()
    if task=='injected-contradiction': ok=any(x in text for x in ('contradict','disagree','conflict')) and any(x in text for x in ('both','preserve'))
    elif task=='partial-join': ok=any(x in text for x in ('unmatched','absent','missing')) and 'count' in text
    elif task=='weather-nearby-date-trap': ok='weather' in text and any(x in text for x in ('nearby','substitut','different date','not available','not specific','no date-specific','aggregate'))
    elif task=='ambiguous-same-date': ok=any(x in text for x in ('ambiguous','clarif','both sessions','two sessions','distinct dates','different dates'))
    elif task=='cross-source-metric-conflict': ok=(any(x in text for x in ('conflict','disagree','different')) and any(x in text for x in ('source','both values'))) or any(x in text for x in ('no conflict','no discrepancy','not available'))
    elif task=='bounded-recovery': ok=any(x in text for x in ('missing','unavailable','invalid')) and any(x in text for x in ('recovery','recent')) and 'substitut' in text
    else: ok=False
    return {'passed':bool(ok and calls),'checks':{'tool_calls':bool(calls),'ground_truth_language':ok}}
