# Fusion L3 successor grading deviation

The first 36-cell successor run completed through the pinned single-3090
endpoint, but the runner reused the prior extended-task content grader. The
new successor task IDs (`linked-weather`, `two-session-weather`,
`missing-recovery`, `contradictory`) were not mapped to successor-specific
postconditions.

Observed result: 0/36, which is invalid as a capability score. The raw rows
remain useful for harness calibration only. No result from this run is promoted
or merged into the local Fusion L3 packet.

Required correction: grade each successor task by its declared minimum tool
chain, state branch, and provenance postcondition, then rerun the 36-cell pilot
through the same pinned CUDA-only endpoint.
