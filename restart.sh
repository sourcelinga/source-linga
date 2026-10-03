#!/bin/bash
# Restart the Forge background service (picks up code changes). launchd relaunches Forge.app.
pkill -f "[M]acOS/Python -m forge.server"
for i in $(seq 1 40); do curl -sf -m 2 http://127.0.0.1:8777/api/status >/dev/null && { echo "Forge restarted"; exit 0; }; sleep 2; done
echo "Forge did not come back; see data/server.log"; exit 1
