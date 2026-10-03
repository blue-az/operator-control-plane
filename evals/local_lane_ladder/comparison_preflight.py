"""Fail-closed checks for a prospective pinned comparison (not legacy regrading).

No model generation or tag mutation. Stored tags, outbound OpenAI request fields,
and attributed remote placement are separate checks; none substitutes for another.
"""
from __future__ import annotations

import json
import re
from typing import Any

# Ollama 0.32.12 api.Options predict fields, plus explicit context and speculation.
# Stop sequences are model-specific template semantics, declared per model.
PIN_FIELDS = frozenset({
    "num_ctx", "num_keep", "num_predict", "seed", "temperature", "top_k", "top_p",
    "min_p", "typical_p", "repeat_last_n", "repeat_penalty", "presence_penalty",
    "frequency_penalty", "draft_num_predict",
})
REQUEST_FIELDS = {
    "temperature": "temperature", "top_p": "top_p", "seed": "seed",
    "frequency_penalty": "frequency_penalty", "presence_penalty": "presence_penalty",
    "max_tokens": "num_predict",
}


class PreflightError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PreflightError(message)


def parse_parameters(text: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        fields = line.strip().split(None, 1)
        require(len(fields) == 2, f"malformed parameter line: {line!r}")
        key, raw = fields
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise PreflightError(f"unparseable parameter {key}: {raw!r}") from exc
        if key == "stop":
            require(isinstance(value, str), "stop must be a string")
            result.setdefault("stop", []).append(value)
        else:
            require(key not in result, f"duplicate parameter: {key}")
            result[key] = value
    return result


# llama-server contracts: the same sampler pin minus Ollama-only fields. num_keep
# has no effect with context shift disabled, and speculation is pinned off
# through /props instead of draft_num_predict.
LLAMA_SCHEMA = "local-lane-comparison/llama-server-v1"
LLAMA_PIN_FIELDS = PIN_FIELDS - {"num_keep", "draft_num_predict"}
# /props default_generation_settings.params key for each pin field (num_ctx and
# num_predict are checked separately: n_ctx, and max_tokens on every request).
PROPS_FIELDS = {
    "seed": "seed", "temperature": "temperature", "top_k": "top_k", "top_p": "top_p",
    "min_p": "min_p", "typical_p": "typical_p", "repeat_last_n": "repeat_last_n",
    "repeat_penalty": "repeat_penalty", "presence_penalty": "presence_penalty",
    "frequency_penalty": "frequency_penalty",
}


def validate_llama_contract(contract: dict) -> None:
    parameters = contract.get("parameters", {})
    require(set(parameters) == LLAMA_PIN_FIELDS, "contract must explicitly declare every pin field and no others")
    for key, value in parameters.items():
        require(type(value) in (int, float), f"{key} must be numeric")
        require(float('-inf') < value < float('inf'), f"{key} must be finite")
    require(parameters['num_ctx'] > 0 and parameters['num_predict'] > 0, "positive context/output limits required")
    require(contract.get("think") == "off", "llama-server contracts support the thinking-off profile only")
    engine = contract.get("engine", {})
    require(bool(engine.get("release")) and bool(re.fullmatch(r"[a-f0-9]{64}", str(engine.get("archive_sha256", "")))),
            "declare engine release and archive_sha256")
    models = contract.get("models", {})
    require(bool(models), "empty model roster")
    for tag, model in models.items():
        require(isinstance(tag, str) and bool(tag), "empty model tag")
        require(bool(re.fullmatch(r"[a-f0-9]{64}", str(model.get("gguf_sha256", "")))), f"{tag}: missing full gguf_sha256")
        require(type(model.get("gguf_bytes")) is int and model["gguf_bytes"] > 0, f"{tag}: declare gguf_bytes")
        require(isinstance(model.get("gguf_path"), str) and model["gguf_path"].startswith("/"), f"{tag}: declare absolute gguf_path")
        require(model.get("variant") in ("instruct", "hybrid"), f"{tag}: declare variant")
        # A model deliberately split across GPU and CPU (MoE experts on CPU to fit a
        # smaller card) declares its own lower bound and a hard ceiling.
        override = model.get("placement", {})
        require(set(override) <= {"minimum_weight_allocation_ratio", "maximum_mib"}, f"{tag}: unknown placement override")
        if "maximum_mib" in override:
            require(type(override["maximum_mib"]) in (int, float) and override["maximum_mib"] > 0, f"{tag}: maximum_mib must be positive")
    clock = contract.get("placement", {}).get("memory_clock_mhz")
    require(clock is None or type(clock) is int, "memory_clock_mhz must be an integer when declared")


def validate_llama_props(contract: dict, tag: str, props: dict, gguf: dict) -> dict:
    """Check the live server's own report and a fresh hash of the file it loaded."""
    validate_contract(contract)
    require(contract.get("schema") == LLAMA_SCHEMA, "not a llama-server contract")
    require(tag in contract["models"], "model is outside the frozen roster")
    expected = contract["models"][tag]
    require(props.get("model_alias") == tag, f"{tag}: server alias is {props.get('model_alias')!r}")
    require(props.get("model_path") == expected["gguf_path"], f"{tag}: server loaded {props.get('model_path')!r}")
    require(gguf.get("path") == expected["gguf_path"], f"{tag}: hashed a different file")
    require(gguf.get("sha256") == expected["gguf_sha256"], f"{tag}: gguf sha256 mismatch")
    require(gguf.get("bytes") == expected["gguf_bytes"], f"{tag}: gguf size mismatch")
    require(props.get("total_slots") == 1, f"{tag}: expected exactly one slot")
    settings = props.get("default_generation_settings", {})
    require(settings.get("n_ctx") == contract["parameters"]["num_ctx"],
            f"{tag}: n_ctx {settings.get('n_ctx')!r} != {contract['parameters']['num_ctx']}")
    params = settings.get("params", {})
    for pin_key, props_key in PROPS_FIELDS.items():
        value = params.get(props_key)
        # /props reports float32 values (0.7 -> 0.699999988...).
        require(type(value) in (int, float) and abs(value - contract["parameters"][pin_key]) < 1e-6,
                f"{tag}: {pin_key} expected {contract['parameters'][pin_key]!r}, observed {value!r}")
    require(params.get("speculative.types") == "none", f"{tag}: speculative decoding is not off")
    for key, neutral in (("dry_multiplier", 0), ("xtc_probability", 0), ("mirostat", 0), ("top_n_sigma", -1)):
        require(params.get(key) == neutral, f"{tag}: {key} is {params.get(key)!r}, expected {neutral!r}")
    require(params.get("lora") == [], f"{tag}: adapters loaded")
    return {"model": tag, "gguf_sha256": gguf["sha256"], "n_ctx": settings["n_ctx"],
            "params": {k: params[k] for k in PROPS_FIELDS.values()}}


def validate_llama_placement(contract: dict, tag: str, remote: dict) -> dict:
    """All GPU memory of the serving process on the one declared card."""
    validate_contract(contract)
    expected = contract.get("placement", {})
    require(remote.get("host") == expected.get("host") and bool(expected.get("host")), "remote host mismatch")
    require(remote.get("port") == expected.get("port") and type(expected.get("port")) is int, "remote listener port mismatch")
    gpu = expected.get("gpu_uuid")
    require(isinstance(gpu, str) and gpu.startswith("GPU-"), "declare exactly one allowed GPU UUID")
    daemon = remote.get("listener_pid")
    require(type(daemon) is int and daemon > 0, "no attributed remote listener")
    allocated = {}
    for app in remote.get("compute_apps", []):
        if int(app["pid"]) != daemon:
            require(float(app["used_mib"]) <= 64, "unrelated GPU workload present; do not evict it")
            continue
        allocated[app["gpu_uuid"]] = allocated.get(app["gpu_uuid"], 0.0) + float(app["used_mib"])
    require(set(allocated) == {gpu}, f"server allocated on {sorted(allocated)}, expected only {gpu}")
    override = contract["models"][tag].get("placement", {})
    ratio = override.get("minimum_weight_allocation_ratio", expected.get("minimum_weight_allocation_ratio"))
    require(type(ratio) in (int, float) and 0 < ratio <= 1, "declare minimum allocation ratio")
    share = allocated[gpu] * 2**20 / contract["models"][tag]["gguf_bytes"]
    require(share >= ratio, f"attributed allocation below bound: {share:.3f} < {ratio}")
    ceiling = override.get("maximum_mib")
    if ceiling is not None:
        require(allocated[gpu] <= ceiling, f"attributed allocation {allocated[gpu]:.0f} MiB above ceiling {ceiling}")
    clock = expected.get("memory_clock_mhz")
    if clock is not None:
        observed = remote.get("memory_clock_mhz", {}).get(gpu)
        require(observed == clock, f"GPU memory clock {observed!r} MHz, contract requires {clock}")
    return {"proved": True, "host": remote["host"], "listener_pid": daemon, "gpu_uuid": gpu,
            "attributed_mib": allocated[gpu], "weight_allocation_ratio": share,
            "maximum_mib": ceiling, "memory_clock_mhz": clock}


def validate_contract(contract: dict) -> None:
    if contract.get("schema") == LLAMA_SCHEMA:
        validate_llama_contract(contract)
        return
    require(contract.get("schema") == "local-lane-comparison/v1", "unknown comparison schema")
    parameters = contract.get("parameters", {})
    require(set(parameters) == PIN_FIELDS, "contract must explicitly declare every pin field and no others")
    for key, value in parameters.items():
        require(type(value) in (int, float), f"{key} must be numeric")
        require(float('-inf') < value < float('inf'), f"{key} must be finite")
    require(parameters['num_ctx'] > 0 and parameters['num_predict'] > 0, "positive context/output limits required")
    require(contract.get("think") in ("off", "on"), "explicit thinking profile required")
    require(contract.get("ollama_version") == "0.32.12", "review option contract before using another Ollama version")
    models = contract.get("models", {})
    require(bool(models), "empty model roster")
    for tag, model in models.items():
        require(isinstance(tag, str) and bool(tag), "empty model tag")
        for field in ("digest", "weight_sha256"):
            require(bool(re.fullmatch(r"[a-f0-9]{64}", str(model.get(field, "")))), f"{tag}: missing full {field}")
        require(model.get("variant") in ("instruct", "thinking", "hybrid"), f"{tag}: declare variant")
        require(isinstance(model.get("stop"), list) and all(isinstance(s, str) for s in model["stop"]), f"{tag}: declare stop sequences")
        require(not (model["variant"] == "thinking" and contract["think"] == "off"), f"{tag}: reasoning-only variant cannot enter the thinking-off cohort")


def validate_model_snapshot(contract: dict, tag: str, snapshot: dict) -> dict:
    validate_contract(contract)
    require(tag in contract["models"], "model is outside the frozen roster")
    expected = contract["models"][tag]
    require(snapshot.get("ollama_version") == contract["ollama_version"], "serving version changed")
    require(snapshot.get("name") == tag, "model tag mismatch")
    require(snapshot.get("digest") == expected["digest"], f"{tag}: tag digest changed")
    show = snapshot["show"]
    blobs = re.findall(r"^FROM .*sha256-([a-f0-9]{64})\s*$", show.get("modelfile", ""), re.MULTILINE)
    # A model may carry declared auxiliary blobs (e.g. a vision projector); any
    # undeclared or missing blob still fails.
    extra = expected.get("extra_blob_sha256s", [])
    require(isinstance(extra, list), f"{tag}: extra_blob_sha256s must be a list")
    require(blobs == [expected["weight_sha256"], *extra], f"{tag}: model weight blob mismatch or absent")
    actual = parse_parameters(show.get("parameters", ""))
    for key, value in contract["parameters"].items():
        require(key in actual and type(actual[key]) in (int, float) and actual[key] == value,
                f"{tag}: {key} expected {value!r}, observed {actual.get(key, '<unset>')!r}")
    require(actual.get("stop", []) == expected["stop"], f"{tag}: stop sequences changed")
    # No unreviewed runtime overrides can hide outside the contract.
    require(set(actual) <= PIN_FIELDS | {"stop"}, f"{tag}: undeclared runtime parameters {sorted(set(actual) - PIN_FIELDS - {'stop'})}")
    capabilities = set(show.get("capabilities", []))
    require({"completion", "tools"} <= capabilities, f"{tag}: required capabilities absent")
    if contract["think"] == "on":
        require("thinking" in capabilities, f"{tag}: thinking requested but unsupported")
    return {"model": tag, "digest": expected["digest"], "weight_sha256": blobs[0], "parameters": actual}


def validate_request(contract: dict, payload: dict) -> None:
    """Validate the actual outgoing /v1/chat/completions body, not Pi CLI intent."""
    validate_contract(contract)
    require(payload.get("model") in contract["models"], "outbound model outside roster")
    for request_key, pin_key in REQUEST_FIELDS.items():
        require(request_key in payload and type(payload[request_key]) in (int, float)
                and payload[request_key] == contract["parameters"][pin_key],
                f"outbound {request_key} must explicitly equal {contract['parameters'][pin_key]!r}")
    effort = "none" if contract["think"] == "off" else "medium"
    require(payload.get("reasoning_effort") == effort, f"outbound reasoning_effort must explicitly be {effort}")
    # Do not let another dialect bypass the fields validated above.
    allowed = {"model", "messages", "tools", "tool_choice", "stream", "stream_options",
               "temperature", "top_p", "seed", "frequency_penalty", "presence_penalty",
               "max_tokens", "reasoning_effort"}
    require(set(payload) <= allowed, f"unreviewed outbound fields: {sorted(set(payload) - allowed)}")


def validate_remote_placement(contract: dict, tag: str, local_ps: dict, remote: dict) -> dict:
    """Check a fresh SSH snapshot from the serving host, never desktop totals.

    Requires GPU memory attributed to the listening daemon's process ancestry.
    Allocation is a residency plausibility bound, not proof that CPU offload is zero.
    """
    validate_contract(contract)
    expected = contract.get("placement", {})
    require(remote.get("host") == expected.get("host") and bool(expected.get("host")), "remote host mismatch")
    require(remote.get("port") == expected.get("port") and type(expected.get("port")) is int, "remote listener port mismatch")
    local = local_ps.get("models", [])
    loaded = remote.get("api_ps", {}).get("models", [])
    require(len(local) == len(loaded) == 1, "require exactly one loaded model on the study daemon")
    for rows in (local, loaded):
        require(rows[0].get("name") == tag and rows[0].get("digest") == contract["models"][tag]["digest"], "tunnel/remote loaded model identity mismatch")
    require(local[0].get("size") == loaded[0].get("size") and local[0].get("size_vram") == loaded[0].get("size_vram"), "tunnel and remote placement disagree")
    # One card (a single-seat cohort) or both; the declared set is exhaustive.
    declared = expected.get("gpu_uuids", [])
    allowed = set(declared)
    require(len(allowed) == len(declared) and len(allowed) in (1, 2)
            and all(isinstance(g, str) and g.startswith('GPU-') for g in allowed),
            "declare one or two distinct allowed GPU UUIDs")
    inventory = {g["uuid"]: g for g in remote.get("gpus", [])}
    require(allowed <= set(inventory), "expected GPUs absent")
    require(all("RTX 3090" in inventory[g]["name"] for g in allowed), "GPU model mismatch")
    daemon = remote.get("listener_pid")
    require(type(daemon) is int and daemon > 0, "no attributed remote listener")
    # Parent relationships must reach the actual listener, not a caller-supplied PID list.
    parents = {int(p["pid"]): int(p["ppid"]) for p in remote.get("processes", [])}
    owned = {daemon}
    while True:
        more = {pid for pid, ppid in parents.items() if ppid in owned}
        if more <= owned:
            break
        owned |= more
    allocated = {}
    for app in remote.get("compute_apps", []):
        if int(app["pid"]) not in owned:
            require(float(app["used_mib"]) <= 64, "unrelated GPU workload present; do not evict it")
            continue
        require(app["gpu_uuid"] in allowed, "study daemon allocated outside allowed GPU set")
        allocated[app["gpu_uuid"]] = allocated.get(app["gpu_uuid"], 0.0) + float(app["used_mib"])
    require(bool(allocated), "no attributed study allocation")
    ratio = expected.get("minimum_weight_allocation_ratio")
    require(type(ratio) in (int, float) and 0 < ratio <= 1, "declare minimum allocation ratio")
    weight_bytes = contract["models"][tag].get("weight_bytes")
    require(type(weight_bytes) is int and weight_bytes > 0, "declare weight blob bytes")
    share = sum(allocated.values()) * 2**20 / weight_bytes
    require(share >= ratio, f"attributed allocation below bound: {share:.3f} < {ratio}")
    return {"proved": True, "host": remote["host"], "listener_pid": daemon,
            "attributed_mib_by_gpu": allocated, "weight_allocation_ratio": share,
            "zero_cpu_offload_proved": False}
