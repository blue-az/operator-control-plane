import json
import tempfile
from pathlib import Path

import gated_runner


def mock_agent_success(artifact_path: Path):
    # Simulates a successful anchored edit
    artifact_path.write_text("Correct content: The output is OK")
    return 2, "success"

def mock_agent_raw_fail(artifact_path: Path):
    # Simulates the "Raw Edit" failure: writes something that's almost right
    # but fails the gate (which expects "OK")
    artifact_path.write_text("Incorrect content: The output is almost OK")
    return 5, "success"

def mock_agent_timeout(artifact_path: Path):
    # Simulates a timeout: does nothing
    return 0, "timeout"

def run_experiment_case(case_name, agent_fn, cell_data, artifact_content):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        artifact_path = root / "artifact.txt"
        artifact_path.write_text(artifact_content)
        
        # Update the gate command to use the absolute path of the temporary artifact
        cell_data["gate"] = {
            "command": ["sh", "-c", f"grep -q 'OK' {artifact_path} && echo 'OK'"], 
            "expect": "OK"
        }
        
        # Setup cell
        cell_path = root / "cell.json"
        cell_path.write_text(json.dumps(cell_data))
        cell = gated_runner.load_cell(str(cell_path))
        
        # Define the action callback for the runner
        def action_callback():
            return agent_fn(artifact_path)
            
        record = gated_runner.run_invocation(
            cell=cell,
            harness="mock-harness",
            model="mock-model",
            action_callback=action_callback,
            artifact_path=artifact_path
        )
        return record

if __name__ == "__main__":
    # The Gate: expect "OK"
    cell_data = {
        "cell_id": "r3-test-01",
        "objective": "Change state to OK",
        "brief": "Update artifact.txt to contain 'OK'",
        "workspace": ".",
    }

    cases = [
        ("Success (Anchored)", mock_agent_success),
        ("Failure (Raw/Drift)", mock_agent_raw_fail),
        ("Failure (Timeout)", mock_agent_timeout),
    ]

    cell_data["gate"] = {"command": ["sh", "-c", "grep -q 'OK' artifact.txt && echo 'OK'"], "expect": "OK"}

    cases = [
        ("Success (Anchored)", mock_agent_success),
        ("Failure (Raw/Drift)", mock_agent_raw_fail),
        ("Failure (Timeout)", mock_agent_timeout),
    ]

    print(f"{'Case':<25} | {'Verdict':<10} | {'Hash Changed':<12} | {'Calls':<6} | {'Cause':<10}")
    print("-" * 70)
    
    for name, agent in cases:
        rec = run_experiment_case(name, agent, cell_data, "Initial state: Fail")
        print(f"{name:<25} | {rec.gate_verdict:<10} | {rec.artifact_hash_changed!s:<12} | {rec.tool_call_count:<6} | {rec.exit_cause:<10}")
