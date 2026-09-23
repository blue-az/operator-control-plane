import json, os, sys, time, urllib.request, urllib.error
KEY = open(os.path.expanduser("~/.config/openrouter/api_key")).read().strip()
EV = "/home/blueaz/operator-control-plane/evals/"
ROUNDS = {"R3": "bt_describe_20260921", "R4": "operator_describe_20260921"}
RUBRIC = ("Judge fidelity to the brief: a mechanical description; a demonstrated-versus-asserted split with "
          "passages quoted; specific unknowns with what would settle them; a misreading genuinely invited by the text; "
          "no invented mechanisms, numbers, or claims borrowed from the wrong source; findings not softened.")
LEVELS = ["Overclaims or invents; loose with sources", "Mostly careful with some overreach", "Careful, precise, well-sourced; no apparent overreach"]

def call(state, labels):
    q = {"best": {"type": "choice", "instructions": "Which answer is best? " + RUBRIC,
                  "criteria": {l: f"Answer {l}" for l in labels}},
         "worst": {"type": "choice", "instructions": "Which answer is worst? " + RUBRIC,
                   "criteria": {l: f"Answer {l}" for l in labels}}}
    for l in labels:
        q[f"score_{l}"] = {"type": "score", "instructions": f"Rate answer {l} only. " + RUBRIC, "criteria": LEVELS}
    body = json.dumps({"model": "typesafe/jev-1.13", "state": state, "questions": q}).encode()
    req = urllib.request.Request("https://openrouter.ai/api/alpha/decisions", data=body,
          headers={"Authorization": "Bearer " + KEY, "Content-Type": "application/json"})
    t = time.time()
    with urllib.request.urlopen(req, timeout=120) as r: out = json.loads(r.read())
    out["_secs"] = round(time.time() - t, 2)
    return out

results = []; total = 0.0
for rnd, d in ROUNDS.items():
    brief = open(EV + d + "/ANALYST_BRIEF.md").read()
    ans = {l: open(EV + d + f"/judge/{l}.md").read() for l in "ABC"}
    key = dict(line.strip().split(" = ") for line in open(EV + d + "/KEY.txt") if "=" in line)
    setups = {"orig": ({"A": "A", "B": "B", "C": "C"}),            # label -> original letter
              "shuffled": ({"X": "C", "Y": "A", "Z": "B"})}
    for name, lab in setups.items():
        state = {"brief": brief, "answers": {L: ans[o] for L, o in lab.items()}}
        for rep in range(3):
            out = call(state, list(lab))
            a = out["answers"]; total += out["usage"]["cost"]
            model = lambda L: key[lab[L]]
            row = {"round": rnd, "setup": name, "rep": rep, "secs": out["_secs"],
                   "best": model(a["best"]["choice"]), "best_p": {model(k): v for k, v in a["best"]["probabilities"].items()},
                   "worst": model(a["worst"]["choice"]), "worst_p": {model(k): v for k, v in a["worst"]["probabilities"].items()},
                   "scores": {model(L): a[f"score_{L}"]["score"] for L in lab},
                   "conf": {model(L): a[f"score_{L}"].get("confidence") for L in lab}}
            results.append(row); print(json.dumps(row), flush=True)
json.dump(results, open(sys.argv[1], "w"), indent=1)
print(f"total cost ${total:.6f}")
