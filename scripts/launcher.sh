#!/bin/bash

SESSION="NETATMO"

# Wait a bit for system to fully initialize
sleep 5

# Ensure tmux is available
if ! command -v tmux &> /dev/null; then
    echo "tmux not found, exiting"
    exit 1
fi

echo "Launching tmux"
# allow re-launch
tmux has-session -t $SESSION 2>/dev/null && tmux kill-session -t $SESSION

# Create new detached session
tmux new-session -d -s $SESSION "python3 ~/netatmo/src/netatmo.py"

# Verify session was created
if tmux has-session -t $SESSION 2>/dev/null; then
    echo "tmux session $SESSION started successfully"
else
    echo "Failed to start tmux session $SESSION"
    exit 1
fi

# Attach to the session (commented out for rc.local usage)
# tmux attach-session -t $SESSION

# To detach from the tmux session, press: Ctrl+B, then d