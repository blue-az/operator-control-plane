#!/usr/bin/env python3
"""Grade the ATS cartoon case study with qwen3-vl:30b.

Paper 1.37 (and the frontier-vs-local composite) claims a visual split:
frontier / tag-heavy 26b keeps a child's tricycle; narrative / local
bleeds to a bicycle and loses the elephant-as-rider. This pack sends
the existing stills (not regenerated) via /api/chat images= and grades
message.content only.

Gold is operator-pixel on these files, not the paper sentence. The Jun 4
12b/26b pair is a later SDXL regen from prompts_compare.json.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import shutil
import subprocess
import time
from datetime import UTC, datetime, timezone
from pathlib import Path

import requests
from PIL import Image

HERE = Path(__file__).resolve().parent
PACK = HERE / "fixtures" / "vl-casestudy"
MODEL = "qwen3-vl:30b"
API = "http://127.0.0.1:11434/api/chat"
NUM_CTX = 16384
NUM_PREDICT = 256
TEMP = 0.8

SRC = {
    "frontier": Path("/home/blueaz/Downloads/Elephant struggles with ATS tricycle.png"),
    "local": Path("/home/blueaz/Python/Evaluation/ComfyUI/output/ats_cartoon_draft_00001_.png"),
    "comfy12b": Path("/home/blueaz/Python/Evaluation/ComfyUI/output/ats_cartoon_12b_00001_.png"),
    "comfy26b": Path("/home/blueaz/Python/Evaluation/ComfyUI/output/ats_cartoon_26b_00001_.png"),
    "composite": Path(
        "/home/blueaz/Python/Evaluation/ComfyUI/output/frontier_vs_local_elephants_corrected.png"
    ),
}

SINGLE_PROMPT = (
    "Look at this image. Reply with exactly four labels separated by spaces, nothing else.\n"
    "1. ELEPHANT or NO-ELEPHANT\n"
    "2. ELEPHANT-RIDER or OTHER-RIDER or NO-RIDER\n"
    "3. TRICYCLE or BICYCLE or CART or NONE\n"
    "4. COLOR or MONO"
)

COMPOSITE_PROMPT = (
    "This is a two-panel figure. The left panel is labeled Frontier. "
    "The right panel is labeled Local. "
    "Which panel shows an elephant riding a child's tricycle? "
    "Reply with only one word: FRONTIER, LOCAL, BOTH, or NEITHER."
)

# Operator gold from the pixels in SRC, 2026-08-15. Not the paper's prose.
STILLS = [
    {
        "id": "frontier",
        "prompt": SINGLE_PROMPT,
        "facets": {
            "subject": "ELEPHANT",
            "rider": "ELEPHANT-RIDER",
            "vehicle": "TRICYCLE",
            "chroma": "COLOR",
        },
        "note": "color cartoon; elephant in suit on a yellow child's tricycle; ATS on the frame",
    },
    {
        "id": "local",
        "prompt": SINGLE_PROMPT,
        "facets": {
            "subject": "ELEPHANT",
            "rider": "OTHER-RIDER",
            "vehicle": "BICYCLE",
            "chroma": "MONO",
        },
        "note": "B&W; elephant not the rider; a small human on a 2-wheel bicycle",
    },
    {
        "id": "comfy12b",
        "prompt": SINGLE_PROMPT,
        "facets": {
            "subject": "ELEPHANT",
            "rider": "ELEPHANT-RIDER",
            "vehicle": "TRICYCLE",
            "chroma": "MONO",
        },
        "note": "Jun 4 SDXL from 12b narrative prompt; 3 wheels visible; elephant riding",
    },
    {
        "id": "comfy26b",
        "prompt": SINGLE_PROMPT,
        "facets": {
            "subject": "ELEPHANT",
            "rider": "ELEPHANT-RIDER",
            "vehicle": "CART",
            "chroma": "MONO",
        },
        "note": "Jun 4 SDXL from 26b tag prompt; 2 large wheels, wagon/cart, garbled BUUCKINS",
    },
    {
        "id": "composite",
        "prompt": COMPOSITE_PROMPT,
        "facets": {"panel": "FRONTIER"},
        "note": "left=frontier trike (color); right=local bicycle (mono)",
    },
]


def nvidia_smi_text() -> str:
    return subprocess.check_output(["nvidia-smi"], text=True)


def placement() -> str:
    out = subprocess.run(["ollama", "ps"], capture_output=True, text=True).stdout
    lines = [ln for ln in out.splitlines() if ln.strip()]
    if len(lines) < 2:
        return "none"
    parts = lines[1].split()
    for i, p in enumerate(parts):
        if "%" in p:
            return " ".join(parts[i : i + 2])
    return lines[1]


def stage_stills(stills_dir: Path) -> None:
    stills_dir.mkdir(parents=True, exist_ok=True)
    for key, src in SRC.items():
        dest = stills_dir / f"{key}.png"
        if key == "composite":
            im = Image.open(src).convert("RGB")
            im.thumbnail((1280, 768), Image.Resampling.LANCZOS)
            im.save(dest, "PNG")
        else:
            shutil.copy2(src, dest)


def b64_png(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def chat(model: str, prompt: str, image_b64: str | None) -> dict:
    msg: dict = {"role": "user", "content": prompt}
    if image_b64 is not None:
        msg["images"] = [image_b64]
    body = {
        "model": model,
        "stream": False,
        "think": False,
        "keep_alive": "5m",
        "options": {"num_ctx": NUM_CTX, "temperature": TEMP, "num_predict": NUM_PREDICT},
        "messages": [msg],
    }
    start = time.monotonic()
    r = requests.post(API, json=body, timeout=600)
    wall = time.monotonic() - start
    r.raise_for_status()
    d = r.json()
    m = d.get("message") or {}
    ev, ed = d.get("eval_count") or 0, d.get("eval_duration") or 0
    content = m.get("content") or ""
    thinking = m.get("thinking") or ""
    return {
        "wall_s": round(wall, 2),
        "eval_count": ev,
        "eval_duration_s": round(ed / 1e9, 3) if ed else None,
        "tok_s": round(ev / (ed / 1e9), 1) if ed else None,
        "prompt_eval_count": d.get("prompt_eval_count"),
        "done_reason": d.get("done_reason"),
        "response": content,
        "thinking_chars": len(thinking),
        "response_chars": len(content),
        "placement": placement(),
        "http_ok": True,
    }


def grade(response: str, facets: dict[str, str]) -> dict:
    text = (response or "").strip()
    empty = text == ""
    hits = {}
    upper = text.upper()
    for name, gold in facets.items():
        token = gold.upper()
        hits[name] = bool(re.search(rf"(?<![A-Z0-9-]){re.escape(token)}(?![A-Z0-9-])", upper))
    n = len(facets)
    n_hit = sum(hits.values())
    return {
        "empty": empty,
        "valid_row": not empty,
        "facet_hits": hits,
        "n_hit": n_hit,
        "n_facet": n,
        "all_hit": (not empty) and n_hit == n,
    }


def write_results(rows: list[dict], path: Path) -> None:
    lines = [
        "# VL case study — ATS cartoon / paper 1.37 stills",
        "",
        f"Generated from {len(rows)} cells. Model `{MODEL}`.",
        "Grade is `message.content` only. Gold is operator-pixel on these files.",
        "",
        "## Per cell",
        "",
        "| still | image | t | all | hits | empty | leaky | s | ctok | think_ch | resp_ch | tok/s | place | response |",
        "|---|:---:|---:|:---:|---:|:---:|:---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for r in rows:
        resp = (r.get("response") or "").replace("|", "/").replace("\n", " ")[:80]
        lines.append(
            f"| {r['still']} | {int(r['image'])} | {r['trial']} | "
            f"{'Y' if r['all_hit'] else 'n'} | {r['n_hit']}/{r['n_facet']} | "
            f"{int(r['empty'])} | {int(r['leaky'])} | {r['wall_s']} | {r['eval_count']} | "
            f"{r['thinking_chars']} | {r['response_chars']} | {r['tok_s']} | "
            f"{r['placement']} | {resp} |"
        )
    from collections import defaultdict

    bag: dict[tuple, list] = defaultdict(list)
    for r in rows:
        bag[(r["still"], r["image"])].append(r)
    lines += ["", "## Condition totals (all-facet hit / valid)", ""]
    lines += ["| still | image | all | mean facets | leaky | mean s |", "|---|:---:|---:|---:|---:|---:|"]
    for key in sorted(bag):
        rs = bag[key]
        valid = [x for x in rs if x["valid_row"]]
        all_hit = sum(x["all_hit"] for x in valid)
        mean_f = (
            f"{sum(x['n_hit'] for x in valid) / len(valid):.2f}/{rs[0]['n_facet']}"
            if valid
            else "—"
        )
        leak = sum(x["leaky"] for x in rs)
        walls = [x["wall_s"] for x in rs if x["wall_s"] is not None]
        mean_s = f"{sum(walls) / len(walls):.1f}" if walls else "—"
        still, image = key
        lines.append(
            f"| {still} | {int(image)} | {all_hit}/{len(valid) or 0} | {mean_f} | "
            f"{leak}/{len(rs)} | {mean_s} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--trials", type=int, default=3)
    args = ap.parse_args()

    traces = PACK / "traces"
    stills_dir = PACK / "stills"
    evidence = PACK / "evidence"
    traces.mkdir(parents=True, exist_ok=True)
    evidence.mkdir(parents=True, exist_ok=True)
    stage_stills(stills_dir)

    gold = {
        "captured_utc": datetime.now(UTC).isoformat(),
        "model": args.model,
        "num_ctx": NUM_CTX,
        "num_predict": NUM_PREDICT,
        "source": {k: str(v) for k, v in SRC.items()},
        "stills": [
            {
                **s,
                "path": str(stills_dir / f"{s['id']}.png"),
            }
            for s in STILLS
        ],
        "smi_text": nvidia_smi_text(),
    }
    (PACK / "gold.json").write_text(json.dumps(gold, indent=2), encoding="utf-8")
    (evidence / "prerun.txt").write_text(
        "\n".join(
            [
                f"captured_utc: {datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')}",
                f"git_rev: {subprocess.check_output(['git', '-C', str(HERE.parents[1]), 'rev-parse', 'HEAD'], text=True).strip()}",
                "question: can qwen3-vl:30b grade the ATS cartoon case-study stills (paper 1.37 / frontier vs local)",
                f"model: {args.model}",
                f"design: {len(STILLS)} stills x (img-on n={args.trials}, img-off n=1)",
                "grade: message.content only; gold is operator-pixel",
                nvidia_smi_text(),
            ]
        ),
        encoding="utf-8",
    )

    state_path = PACK / "state.json"
    state = {"results": []}
    if state_path.exists():
        state = json.loads(state_path.read_text())
    done = {(r["still"], r["image"], r["trial"]) for r in state.get("results", [])}

    print(
        f"VL casestudy {args.model} stills={len(STILLS)} n_on={args.trials} n_off=1",
        flush=True,
    )
    for still in STILLS:
        path = stills_dir / f"{still['id']}.png"
        conditions = [(True, t) for t in range(1, args.trials + 1)] + [(False, 1)]
        for image, trial in conditions:
            key = (still["id"], image, trial)
            if key in done:
                print(f"skip {key}", flush=True)
                continue
            tag = f"{still['id']} img={int(image)} t{trial}"
            print(f"[{tag}] running...", flush=True)
            img = b64_png(path) if image else None
            try:
                rec = chat(args.model, still["prompt"], img)
            except Exception as exc:  # noqa: BLE001
                rec = {
                    "wall_s": None,
                    "eval_count": 0,
                    "eval_duration_s": None,
                    "tok_s": None,
                    "prompt_eval_count": None,
                    "done_reason": None,
                    "response": "",
                    "thinking_chars": 0,
                    "response_chars": 0,
                    "placement": placement(),
                    "http_ok": False,
                    "error": f"{type(exc).__name__}: {exc}"[:200],
                }
            g = grade(rec["response"], still["facets"])
            row = {
                "still": still["id"],
                "image": image,
                "think": False,
                "trial": trial,
                "model": args.model,
                "leaky": bool(rec.get("thinking_chars", 0) > 0),
                "gold": still["facets"],
                **g,
                **rec,
                "recorded_utc": datetime.now(UTC).isoformat(),
            }
            state["results"].append(row)
            state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
            (traces / f"{still['id']}__img{int(image)}__t{trial}.json").write_text(
                json.dumps(row, indent=2), encoding="utf-8"
            )
            write_results(state["results"], PACK / "RESULTS.md")
            print(
                f"[{tag}] all={row['all_hit']} {row['n_hit']}/{row['n_facet']} "
                f"leaky={row['leaky']} {row['wall_s']}s {row.get('response', '')[:60]!r}",
                flush=True,
            )
    write_results(state["results"], PACK / "RESULTS.md")
    print(f"Wrote {PACK / 'RESULTS.md'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
