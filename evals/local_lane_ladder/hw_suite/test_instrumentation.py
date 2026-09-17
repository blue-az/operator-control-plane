import importlib.util
from pathlib import Path


_spec = importlib.util.spec_from_file_location("suite", Path(__file__).with_name("suite.py"))
suite = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(suite)


def test_moe_fit_decision_is_recorded(tmp_path):
    log = tmp_path / "ollama.log"
    log.write_text(
        "load_tensors: loading model tensors\n"
        "common_params_fit_impl: getting device memory data with all MoE tensors moved to system memory:\n"
        "load_tensors: offloaded 31/31 layers to GPU\n"
        "load_tensors:   CPU_Mapped model buffer size =   748.00 MiB\n"
        "load_tensors:        CUDA0 model buffer size = 16147.43 MiB\n"
        "llama_context: done\n"
    )
    got = suite.read_load_memory(str(log))
    assert got["moe_fit_evidence"] == "experts_host"
    assert got["expert_residency_proven"] is False


def test_missing_moe_fit_evidence_is_not_proof(tmp_path):
    log = tmp_path / "ollama.log"
    log.write_text(
        "load_tensors: loading model tensors\n"
        "load_tensors: offloaded 31/31 layers to GPU\n"
        "load_tensors:   CPU_Mapped model buffer size =   748.00 MiB\n"
        "load_tensors:        CUDA0 model buffer size = 16147.43 MiB\n"
        "llama_context: done\n"
    )
    got = suite.read_load_memory(str(log))
    assert got["moe_fit_evidence"] == "not_present"
    assert got["expert_residency_proven"] is False
