# z13-l2 — take over

```bash
ssh z13 -t tmux attach -t z13-l2
```

Detach: `C-b d`. Resume: same attach.

Pack ledger (not the main z13 `.operator/`):
`evals/local_lane_ladder/fixtures/z13-l2/.operator`

```bash
cd /home/blueaz/operator-control-plane/evals/local_lane_ladder/fixtures/z13-l2
/home/blueaz/operator-control-plane/operator task-show z13-l2-seat
```

Runner skips completed cells. If you set performance, ctrl-c and restart.
