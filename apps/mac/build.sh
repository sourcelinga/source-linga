#!/bin/bash
# Builds "Source Linga.app" (Apple silicon + Intel, macOS 14 Sonoma or newer) from the shared Swift code in
# apps/apple/SourceLinga.swiftpm. Needs only Apple's free Command Line Tools (xcode-select --install), not Xcode.
#   bash apps/mac/build.sh            -> dist/Source Linga.app and dist/SourceLinga-mac.zip
#   bash apps/mac/build.sh --install  -> also copies the app to ~/Applications and opens it
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
SRC="$ROOT/apps/apple/SourceLinga.swiftpm/Sources/App"
OUT="$ROOT/dist"
APP="$OUT/Source Linga.app"
VERSION="2.0.0"

command -v swiftc >/dev/null || { echo "Install Apple's Command Line Tools first:  xcode-select --install"; exit 1; }

# SwiftUI's newest SDKs need macros that ship only with Xcode; Command Line Tools still include the
# macOS 26 SDK, which builds the same app. Prefer it when Xcode isn't the active developer directory.
SDK="$(xcrun --show-sdk-path)"
if ! xcode-select -p | grep -q Xcode.app; then
  for s in /Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk /Library/Developer/CommandLineTools/SDKs/MacOSX26.sdk \
           /Library/Developer/CommandLineTools/SDKs/MacOSX15*.sdk; do
    [ -d "$s" ] && { SDK="$s"; break; }
  done
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
echo "Building Source Linga $VERSION with $(basename "$SDK")…"
for ARCH in arm64 x86_64; do
  swiftc -O -swift-version 5 -parse-as-library -sdk "$SDK" -target "$ARCH-apple-macos14.0" \
    -module-name SourceLinga "$SRC"/*.swift -o "$TMP/SourceLinga-$ARCH" 2>&1 | grep -v "warning:\|^\s*|\|^$" || true
  [ -f "$TMP/SourceLinga-$ARCH" ] || { echo "Build failed ($ARCH)."; exit 1; }
done

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
lipo -create "$TMP/SourceLinga-arm64" "$TMP/SourceLinga-x86_64" -output "$APP/Contents/MacOS/SourceLinga"
cp "$SRC/Resources/logo.png" "$APP/Contents/Resources/logo.png"
cp "$HERE/AppIcon.icns" "$APP/Contents/Resources/AppIcon.icns"
# The engine travels inside the app, so "Set up on this Mac" needs no download from GitHub and no Terminal.
# Only shipped files: never config.json, house-rules.md, local/, data/ or evals/local-cases.json.
ENG="$APP/Contents/Resources/engine"
mkdir -p "$ENG/evals" "$ENG/prompts" "$ENG/dist"
cp -R "$ROOT/forge" "$ROOT/web" "$ROOT/skills" "$ROOT/workflows" "$ENG/"
cp "$ROOT"/prompts/*.md "$ENG/prompts/"
cp "$ROOT/evals/cases.json" "$ROOT/evals/local-cases.example.json" "$ENG/evals/"
cp "$ROOT"/{install.sh,uninstall.sh,restart.sh,config.example.json,house-rules.example.md,house-rules.template.md,strategies.json,LICENSE,README.md} "$ENG/"
[ -f "$OUT/SourceLinga.apk" ] && cp "$OUT/SourceLinga.apk" "$ENG/dist/"
find "$ENG" \( -name __pycache__ -o -name .DS_Store -o -name '._*' \) -prune -exec rm -rf {} + 2>/dev/null || true
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleIdentifier</key><string>com.sourcelinga.app</string>
  <key>CFBundleName</key><string>Source Linga</string>
  <key>CFBundleDisplayName</key><string>Source Linga</string>
  <key>CFBundleExecutable</key><string>SourceLinga</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>$VERSION</string>
  <key>CFBundleVersion</key><string>$(date +%Y%m%d%H%M)</string>
  <key>LSMinimumSystemVersion</key><string>14.0</string>
  <key>LSApplicationCategoryType</key><string>public.app-category.productivity</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSSupportsAutomaticTermination</key><false/>
  <key>NSLocalNetworkUsageDescription</key><string>Source Linga can use the AI running on another Mac on your Wi-Fi.</string>
  <key>NSBonjourServices</key><array><string>_sourcelinga._tcp</string></array>
  <key>NSAppTransportSecurity</key><dict><key>NSAllowsLocalNetworking</key><true/></dict>
  <key>NSHumanReadableCopyright</key><string>Source Linga · MIT license</string>
</dict></plist>
PLIST
xattr -cr "$APP"   # Finder/download tags would break the signature
codesign --force --deep --sign - "$APP" >/dev/null 2>&1   # ad-hoc signature (free; no Apple developer account)
(cd "$OUT" && rm -f SourceLinga-mac.zip && ditto -c -k --keepParent "Source Linga.app" SourceLinga-mac.zip)
echo "Built: $APP"

if [ "${1:-}" = "--install" ]; then
  mkdir -p "$HOME/Applications"
  pkill -x SourceLinga 2>/dev/null || true
  rm -rf "$HOME/Applications/Source Linga.app"
  cp -R "$APP" "$HOME/Applications/"
  open "$HOME/Applications/Source Linga.app"
  echo "Installed: ~/Applications/Source Linga.app"
fi
