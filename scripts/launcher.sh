#!/bin/bash

SESSION="NETATMO"

echo "Launching tmux"
# allow re-launch
tmux has-session -t $SESSION 2>/dev/null && tmux kill-session -t $SESSION

tmux new-session -d -s $SESSION "python3 ../src/netatmo.py"

# Attach to the session
# tmux attach-session -t $SESSION

# To detach from the tmux session, press: Ctrl+B, then d