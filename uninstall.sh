#!/bin/bash
# Stops and removes the Forge background service. Leaves Ollama, models and data/ in place.
launchctl bootout "gui/$(id -u)/com.forge.localai" 2>/dev/null || true
rm -f "$HOME/Library/LaunchAgents/com.forge.localai.plist"
pkill -f "[F]orge.app/Contents/MacOS/applet" 2>/dev/null || true
pkill -f "[M]acOS/Python -m forge.server" 2>/dev/null || true
rm -rf "$HOME/Applications/Forge.app"
echo "Forge service removed. To remove models too: ollama rm <model>  (or delete ~/.ollama/models)"
