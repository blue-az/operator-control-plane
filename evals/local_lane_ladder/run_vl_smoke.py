#!/usr/bin/env python3
"""Vision smoke for qwen3-vl:30b.

Text-only 128-token generate is not a vision test (empty response, think leak).
This pack sends stills via /api/chat, grades only message.content, and records
think leak, image-omitted controls, residency, and time-to-answer.
"""

from __future__ import annotations

import argparse
import base64
import json
import secrets
import subprocess
import sys
import time
from datetime import UTC, datetime, timezone
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
PACK = HERE / "fixtures" / "vl-smoke"
FONT = "/usr/share/fonts/source-foundry-hack-fonts/Hack-Regular.ttf"
MODEL = "qwen3-vl:30b"
API = "http://127.0.0.1:11434/api/chat"
NUM_CTX = 16384
NUM_PREDICT = 2048
TEMP = 0.8


def nvidia_smi_text() -> str:
    return subprocess.check_output(["nvidia-smi"], text=True)


def placement() -> str:
    out = subprocess.run(["ollama", "ps"], capture_output=True, text=True).stdout
    lines = [ln for ln in out.splitlines() if ln.strip()]
    if len(lines) < 2:
        return "none"
    # PROCESSOR column is after SIZE; keep the GPU/CPU phrase.
    parts = lines[1].split()
    for i, p in enumerate(parts):
        if "%" in p:
            return " ".join(parts[i : i + 2])
    return lines[1]


def render_text_still(path: Path, lines: list[str], *, bg=(16, 18, 22), fg=(220, 220, 220), size=16) -> None:
    font = ImageFont.truetype(FONT, size)
    pad = 24
    dummy = Image.new("RGB", (8, 8))
    d = ImageDraw.Draw(dummy)
    widths, heights = [], []
    for ln in lines:
        box = d.textbbox((0, 0), ln, font=font)
        widths.append(box[2] - box[0])
        heights.append(box[3] - box[1])
    w = max(widths) + pad * 2
    h = sum(heights) + 6 * (len(lines) - 1) + pad * 2
    img = Image.new("RGB", (max(w, 640), max(h, 200)), bg)
    draw = ImageDraw.Draw(img)
    y = pad
    for ln, lh in zip(lines, heights):
        draw.text((pad, y), ln, font=font, fill=fg)
        y += lh + 6
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)


def build_stills(stills_dir: Path) -> list[dict]:
    stills_dir.mkdir(parents=True, exist_ok=True)
    nonce_smi = secrets.token_hex(3).upper()
    nonce_dash = str(800 + int(secrets.token_hex(2), 16) % 200)
    nonce_mark = "PHOENIX-VL-" + secrets.token_hex(2).upper()

    smi = nvidia_smi_text().rstrip().splitlines()
    power = subprocess.check_output(
        ["nvidia-smi", "--query-gpu=power.limit", "--format=csv,noheader"],
        text=True,
    ).strip()
    smi_path = stills_dir / "smi.png"
    render_text_still(smi_path, smi + ["", f"PROBE={nonce_smi}"], size=13)

    dash_path = stills_dir / "dash.png"
    render_text_still(
        dash_path,
        [
            "Grafana  Tempo / AI-Observability",
            "panel: prox-hil-spans",
            f"SPAN_COUNT={nonce_dash}",
            "window: last 15m   status: local-only",
        ],
        bg=(12, 24, 36),
        fg=(180, 220, 255),
        size=22,
    )

    mark_path = stills_dir / "mark.png"
    render_text_still(
        mark_path,
        ["fixture mark", nonce_mark, "do not invent this token"],
        bg=(40, 12, 12),
        fg=(255, 220, 180),
        size=36,
    )

    stills = [
        {
            "id": "smi",
            "path": str(smi_path),
            "gold": nonce_smi,
            "also_visible": power.split()[0],
            "prompt": "This is a screenshot. What is the PROBE token printed at the bottom? Reply with only that token.",
        },
        {
            "id": "dash",
            "path": str(dash_path),
            "gold": nonce_dash,
            "prompt": "This is a monitoring panel. What is the SPAN_COUNT value? Reply with only the number.",
        },
        {
            "id": "mark",
            "path": str(mark_path),
            "gold": nonce_mark,
            "prompt": "What is the fixture mark token in this image? Reply with only that token.",
        },
    ]
    return stills


def b64_png(path: str) -> str:
    return base64.b64encode(Path(path).read_bytes()).decode("ascii")


def chat(model: str, prompt: str, image_b64: str | None, think: bool) -> dict:
    msg: dict = {"role": "user", "content": prompt}
    if image_b64 is not None:
        msg["images"] = [image_b64]
    body = {
        "model": model,
        "stream": False,
        "think": think,
        "keep_alive": "3m",
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


def grade(response: str, gold: str) -> dict:
    text = (response or "").strip()
    empty = text == ""
    hit = (not empty) and (gold.lower() in text.lower())
    return {"empty": empty, "gold_hit": hit, "valid_row": not empty}


def run_cell(still: dict, *, image: bool, think: bool, trial: int, model: str) -> dict:
    img = b64_png(still["path"]) if image else None
    try:
        rec = chat(model, still["prompt"], img, think)
    except Exception as exc:  # noqa: BLE001 — cell stays a row
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
    g = grade(rec["response"], still["gold"])
    leaky = bool(think is False and rec["thinking_chars"] > 0)
    return {
        "still": still["id"],
        "gold": still["gold"],
        "image": image,
        "think": think,
        "trial": trial,
        "model": model,
        "leaky": leaky,
        **g,
        **rec,
        "recorded_utc": datetime.now(UTC).isoformat(),
    }


def write_results(rows: list[dict], path: Path) -> None:
    lines = [
        "# VL smoke — results",
        "",
        f"Generated from {len(rows)} cells. Model `{MODEL}`.",
        "Grade is `message.content` only. Empty response = invalid row.",
        "Image-omitted cells should *not* hit gold (guess / prior).",
        "",
        "## Per cell",
        "",
        "| still | image | think | t | hit | empty | leaky | s | ctok | think_ch | resp_ch | tok/s | place |",
        "|---|:---:|:---:|---:|:---:|:---:|:---:|---:|---:|---:|---:|---:|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['still']} | {int(r['image'])} | {int(r['think'])} | {r['trial']} | "
            f"{'Y' if r['gold_hit'] else 'n'} | {int(r['empty'])} | {int(r['leaky'])} | "
            f"{r['wall_s']} | {r['eval_count']} | {r['thinking_chars']} | {r['response_chars']} | "
            f"{r['tok_s']} | {r['placement']} |"
        )
    lines += ["", "## Condition totals (gold_hit / valid rows)", ""]
    from collections import defaultdict

    bag: dict[tuple, list] = defaultdict(list)
    for r in rows:
        bag[(r["still"], r["image"], r["think"])].append(r)
    lines += [
        "| still | image | think | hit | valid | leaky | mean s |",
        "|---|:---:|:---:|---:|---:|---:|---:|",
    ]
    for key in sorted(bag):
        rs = bag[key]
        valid = [x for x in rs if x["valid_row"]]
        hit = sum(x["gold_hit"] for x in valid)
        leak = sum(x["leaky"] for x in rs)
        walls = [x["wall_s"] for x in rs if x["wall_s"] is not None]
        mean_s = f"{sum(walls)/len(walls):.1f}" if walls else "—"
        still, image, think = key
        lines.append(
            f"| {still} | {int(image)} | {int(think)} | {hit}/{len(valid) or 0} | "
            f"{len(valid)}/{len(rs)} | {leak}/{len(rs)} | {mean_s} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--trials", type=int, default=3)
    args = ap.parse_args()

    traces = PACK / "traces"
    stills_dir = PACK / "stills"
    traces.mkdir(parents=True, exist_ok=True)
    (PACK / "evidence").mkdir(parents=True, exist_ok=True)

    stills = build_stills(stills_dir)
    gold = {
        "captured_utc": datetime.now(UTC).isoformat(),
        "model": args.model,
        "num_ctx": NUM_CTX,
        "num_predict": NUM_PREDICT,
        "stills": stills,
        "smi_text": nvidia_smi_text(),
    }
    (PACK / "gold.json").write_text(json.dumps(gold, indent=2), encoding="utf-8")

    conditions = [
        ("on_off", True, False),
        ("on_on", True, True),
        ("off_off", False, False),
    ]
    state_path = PACK / "state.json"
    state = {"results": []}
    if state_path.exists():
        state = json.loads(state_path.read_text())
    done = {
        (r["still"], r["image"], r["think"], r["trial"])
        for r in state.get("results", [])
    }

    print(
        f"VL smoke {args.model}  stills={len(stills)} conds=3 n={args.trials} "
        f"num_predict={NUM_PREDICT}",
        flush=True,
    )
    for still in stills:
        for _, image, think in conditions:
            for trial in range(1, args.trials + 1):
                key = (still["id"], image, think, trial)
                if key in done:
                    print(f"skip {key}", flush=True)
                    continue
                tag = f"{still['id']} img={int(image)} think={int(think)} t{trial}"
                print(f"[{tag}] running...", flush=True)
                rec = run_cell(still, image=image, think=think, trial=trial, model=args.model)
                state["results"].append(rec)
                state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
                (traces / f"{still['id']}__img{int(image)}__think{int(think)}__t{trial}.json").write_text(
                    json.dumps(rec, indent=2), encoding="utf-8"
                )
                write_results(state["results"], PACK / "RESULTS.md")
                print(
                    f"[{tag}] hit={rec['gold_hit']} empty={rec['empty']} "
                    f"leaky={rec['leaky']} {rec['wall_s']}s "
                    f"think={rec['thinking_chars']} resp={rec['response_chars']}",
                    flush=True,
                )
    write_results(state["results"], PACK / "RESULTS.md")
    print(f"Wrote {PACK / 'RESULTS.md'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
