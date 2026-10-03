#!/usr/bin/env bash
# Start the testbench-native C1 Fusion packet only after the repair cohort wrote DONE.
F=$(dirname "$(readlink -f "$0")")
while kill -0 "$(cat "$F/launcher.pid")" 2>/dev/null; do sleep 10; done
[ -f "$F/DONE" ] || { echo "repair cohort did not finish; native not started"; exit 1; }
ssh testbench 'cd ~/fusion-native-c1-20261001 && FUSION_L3_AGENT_ROOT=$HOME/Python/project-phoenix/domains/SensorAgents/TennisAgent/cockpit_poc/agent setsid nohup python3 -u run_ollama_campaign.py --packet ~/fusion-native-c1-20261001 --fixture ~/operator-control-plane/evals/tennisagent_l3/fusion_l3_v2/fixture-20260921 > run.log 2>&1 < /dev/null & echo NATIVE_STARTED $!'
