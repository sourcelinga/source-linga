#!/bin/bash
# Source Linga installer (Forge engine): Ollama + models + background service. Safe to re-run.
set -euo pipefail
cd "$(dirname "$0")"
HERE="$(pwd)"
[ "$(uname -m)" = "arm64" ] || echo "⚠ This Mac is not Apple Silicon; local models will be very slow."
if [ ! -f config.json ]; then
  cp config.example.json config.json
  # Pick the model this Mac can run comfortably: 9B needs ~16 GB of memory, 4B runs well in 8 GB.
  RAM_GB=$(( $(sysctl -n hw.memsize) / 1073741824 ))
  if [ "$RAM_GB" -lt 14 ]; then
    python3 - <<'PY'
import json
c = json.load(open("config.json"))
c.update(model="qwen3.5:4b", num_ctx=8192, max_model_gb=4.5, candidate_models=["qwen3.5:4b", "gemma4:e4b", "qwen3:4b"])
json.dump(c, open("config.json", "w"), indent=2)
PY
    echo "→ This Mac has ${RAM_GB} GB of memory: using the lighter qwen3.5:4b model"
  fi
fi
[ -f house-rules.md ] || cp house-rules.template.md house-rules.md
mkdir -p data outputs local/workflows local/skills
chmod +x install.sh restart.sh uninstall.sh apps/mac/build.sh apps/android/build.sh 2>/dev/null || true  # GitHub web uploads drop the executable bit
MODEL=$(python3 -c "import json;print(json.load(open('config.json'))['model'])")
EMBED=$(python3 -c "import json;print(json.load(open('config.json'))['embed_model'])")

# Models run from the internal SSD (fast loads). config.json "archive_dir" (external drive)
# keeps retired models so they can be restored without re-downloading.

# 1. Ollama (local model runtime; updates itself)
if [ ! -d /Applications/Ollama.app ] && [ ! -d "$HOME/Applications/Ollama.app" ]; then
  echo "→ Downloading Ollama (~200 MB) from ollama.com"
  TMP=$(mktemp -d)
  curl -fL --progress-bar -o "$TMP/Ollama-darwin.zip" https://ollama.com/download/Ollama-darwin.zip
  DEST=/Applications; [ -w /Applications ] || { DEST="$HOME/Applications"; mkdir -p "$DEST"; }
  ditto -xk "$TMP/Ollama-darwin.zip" "$DEST"
  rm -rf "$TMP"
  echo "  installed to $DEST/Ollama.app"
fi
APP=/Applications/Ollama.app; [ -d "$APP" ] || APP="$HOME/Applications/Ollama.app"
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$APP" 2>/dev/null || true
open -g "$APP"
echo "→ Starting Ollama"
for i in $(seq 1 90); do curl -sf http://127.0.0.1:11434/api/version >/dev/null && break; sleep 1; done
curl -sf http://127.0.0.1:11434/api/version >/dev/null || { echo "✗ Ollama did not start. Open Ollama from Applications once, then try again."; exit 1; }

# 2. Models
for M in "$EMBED" "$MODEL"; do
  echo "→ Pulling $M"
  python3 -c "from forge.llm import Ollama; Ollama().pull('$M', say=print)"
done

# 3. Background service (web app + scheduled auto-updates), starts at login.
#    Wrapped in Forge.app so macOS can grant it Documents access (a bare launchd python is blocked).
APPW="$HOME/Applications/Forge.app"
mkdir -p "$HOME/Applications"
rm -rf "$APPW"
# The applet supervises the server: if python exits (crash or ./restart.sh), it starts again in 5 s.
osacompile -o "$APPW" -e "repeat" -e "try" \
  -e "do shell script \"cd '$HERE' && exec /usr/bin/python3 -m forge.server >> data/server.log 2>&1\"" \
  -e "end try" -e "delay 5" -e "end repeat"
PB=/usr/libexec/PlistBuddy; IP="$APPW/Contents/Info.plist"
$PB -c "Add :LSUIElement bool true" "$IP"
$PB -c "Set :CFBundleIdentifier com.forge.localai" "$IP" 2>/dev/null || $PB -c "Add :CFBundleIdentifier string com.forge.localai" "$IP"
$PB -c "Add :NSDocumentsFolderUsageDescription string 'Forge indexes your project files to give better answers.'" "$IP"
$PB -c "Add :NSRemovableVolumesUsageDescription string 'Forge checks the external drive that stores its models.'" "$IP"
codesign --force --deep -s - "$APPW" 2>/dev/null
PLIST="$HOME/Library/LaunchAgents/com.forge.localai.plist"
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.forge.localai</string>
  <key>ProgramArguments</key><array><string>/usr/bin/open</string><string>-W</string><string>-g</string><string>$APPW</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>30</integer>
</dict></plist>
PL
launchctl bootout "gui/$(id -u)/com.forge.localai" 2>/dev/null || true
pkill -f "[F]orge.app/Contents/MacOS/applet" 2>/dev/null || true
pkill -f "[M]acOS/Python -m forge.server" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "→ Service installed (Forge.app via com.forge.localai). If macOS asks for Documents access, click Allow."

# 4. First index runs inside the service (avoids two processes writing the index at once)
for i in $(seq 1 60); do curl -sf http://127.0.0.1:8777/api/status >/dev/null && break; sleep 2; done
curl -sf http://127.0.0.1:8777/api/status >/dev/null || { echo "✗ The Source Linga service did not start. Details: data/server.log"; exit 1; }
curl -s -X POST -H 'Content-Type: application/json' -d '{"only":["knowledge"],"force":true}' http://127.0.0.1:8777/api/update >/dev/null
echo "→ First index started in the background (watch it in the Knowledge tab)"

# 5. The Mac app (native window, menu bar, ⌥Space). Built here from source, so macOS trusts it right away.
#    Skipped when the Mac app itself runs this installer (its Set up button).
if [ -z "${SL_FROM_APP:-}" ] && command -v swiftc >/dev/null 2>&1; then
  echo "→ Building the Source Linga Mac app"
  bash apps/mac/build.sh --install || echo "  (Mac app build skipped; the web app works the same: http://127.0.0.1:8777/app)"
fi
echo "✓ Source Linga is running. Mac app: ~/Applications/Source Linga.app · web: http://127.0.0.1:8777/app"
echo "  iPhone, iPad, Android: open the Mac app → Tools → Devices and follow the steps there."
