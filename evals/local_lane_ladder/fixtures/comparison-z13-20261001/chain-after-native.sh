#!/usr/bin/env bash
# Start the desktop-driven Z13 repair cohort only after Z13 native r2 finished (same port/iGPU).
Z=$(dirname "$(readlink -f "$0")")
while ssh -o ConnectTimeout=10 z13 'pgrep -f "python3 -u run_z13_campaign.py" >/dev/null'; do sleep 30; done
ssh z13 'test -f ~/fusion-native-z13-20261001-r2/DONE' || { echo "Z13 native r2 did not write DONE; repair not started"; exit 1; }
cd "$Z" && setsid nohup python3 -u launch-z13.py > run.log 2>&1 < /dev/null &
sleep 3; pgrep -f "^python3 -u launch-z13.py" > "$Z/launcher.pid"; echo "Z13_REPAIR_STARTED $(cat $Z/launcher.pid)"
