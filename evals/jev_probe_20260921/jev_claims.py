import json, os, sys, time, urllib.request
KEY = open(os.path.expanduser("~/.config/openrouter/api_key")).read().strip()
IN = "/home/blueaz/operator-control-plane/evals/bt_describe_20260921/inputs/"
P = {"01": "01_bulkhead-tau_home.txt", "02": "02_showcase-agent.txt", "03": "03_tennis-agent.txt", "04": "04_domains.txt",
     "05": "05_local-models.txt", "06": "06_bt-inc-platform.txt", "07": "07_reflect-shelf.txt"}
def ex(page, *ranges):
    lines = open(IN + P[page]).read().splitlines()
    return "\n".join("\n".join(lines[a-1:b]) for a, b in ranges)
# (id, label, claim, page, ranges)  label: True = supported by excerpt, False = unsupported/contradicted, None = borderline
CLAIMS = [
 ("S1", True,  "ShowcaseAgent lists TennisAgent with 171 tools.", "02", [(105,112)]),
 ("S2", True,  "TennisAgent's own page says it has 189 tools.", "03", [(20,24)]),
 ("S3", True,  "The domains page says WQ has 41 tools across 7 projects.", "04", [(134,137)]),
 ("S4", True,  "The Logbook's downstream execution gating is specified but not yet wired.", "01", [(76,78)]),
 ("S5", True,  "Under clean REST capture, the model passes all six probes.", "05", [(57,62)]),
 ("S6", True,  "The score writer verifies that the file was written by reading it back.", "06", [(1774,1779)]),
 ("S7", True,  "BT Inc. is described as fictional, and the manual is not evidence that a real operating company exists.", "06", [(18,26)]),
 ("S8", True,  "tennis-sensor-toolkit is described as covering 192 tools.", "07", [(31,39)]),
 ("S9", True,  "When the score log is missing or unreadable, the desk falls back to an empty score state.", "06", [(1824,1834)]),
 ("S10", True, "TennisAgent's data layer merges 6 databases into a unified SQLite store.", "03", [(132,153)]),
 ("S11", True, "Overall routing accuracy is 80.6%, with 83 of 103 queries routed correctly.", "02", [(190,195)]),
 ("S12", True, "TennisAgent sessions from Apple Watch, Zepp Universal, Babolat PIQ, Garmin HR, and MiiFit are merged into one queryable database.", "03", [(39,45)]),
 ("U1", False, "TennisAgent's own page says it has 171 tools.", "03", [(20,24)]),
 ("U2", False, "The domains page says WQ has 38 tools.", "04", [(134,137)]),
 ("U3", False, "Callers currently enforce the Logbook gate's exit code, so downstream execution is actively blocked.", "01", [(76,78)]),
 ("U4", False, "The corrupted multi-line JSON was caused by the model's own output formatting.", "05", [(57,62)]),
 ("U5", False, "The score writer checks the reviewer's identity before storing the review record.", "06", [(1774,1779)]),
 ("U6", False, "The manual describes Bulkhead Tau's production runtime as desk-first with an unverified shared router.", "06", [(18,26)]),
 ("U7", False, "The Reflect shelf gives TennisAgent 192 tools.", "07", [(31,39),(59,68)]),
 ("U8", False, "When the score log is missing or unreadable, later hypotheses are blocked.", "06", [(1824,1834)]),
 ("U9", False, "TennisAgent's page lists exactly five supported sensors.", "03", [(132,153)]),
 ("U10", False,"The ShowcaseAgent page describes Safe Mode snapshots and refresh pipelines.", "02", [(1,222)]),
 ("U11", False,"Overall routing accuracy is 90%, with 93 of 103 queries routed correctly.", "02", [(190,195)]),
 ("U12", False,"The bt-inc-platform manual is presented as evidence of a real, unified production cockpit.", "06", [(18,26)]),
 ("B1", None,  "The TennisAgent page describes six merged sensor sources.", "03", [(29,45),(132,153)]),
 ("B2", None,  "TennisAgent merges six SQLite databases containing watch, racquet, and fitness data.", "03", [(29,45),(132,153)]),
]
def call(claim, excerpt):
    body = {"model": "typesafe/jev-1.13", "state": {"source_excerpt": excerpt, "claim": claim},
            "questions": {"supported": {"type": "choice",
              "instructions": "Is the claim fully supported by the source excerpt? Judge only what the excerpt says; a claim the excerpt contradicts, or that goes beyond it, is not supported.",
              "criteria": {"supported": "The excerpt states or directly entails the claim", "unsupported": "The excerpt does not state the claim, goes beyond it, or contradicts it"}}}}
    req = urllib.request.Request("https://openrouter.ai/api/alpha/decisions", data=json.dumps(body).encode(),
          headers={"Authorization": "Bearer " + KEY, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r: return json.loads(r.read())
rows = []; cost = 0.0
for cid, label, claim, page, ranges in CLAIMS:
    e = ex(page, *ranges); ps = []
    for rep in range(2):
        out = call(claim, e); cost += out["usage"]["cost"]; ps.append(out["answers"]["supported"]["probabilities"]["supported"])
    rows.append({"id": cid, "label": label, "p": ps, "claim": claim})
    print(f"{cid:4} label={str(label):5} p(supported)={ps}", flush=True)
json.dump(rows, open(sys.argv[1], "w"), indent=1)
print(f"total cost ${cost:.6f}")
