#!/bin/bash
# Builds the Android app (dist/SourceLinga.apk) without Android Studio or Gradle: just the JDK and the
# Android SDK command-line tools (platform 35, build-tools 35). Works on Android 8.0 and newer.
#   ANDROID_HOME=~/Library/Android/sdk JAVA_HOME=/path/to/jdk-17 bash apps/android/build.sh
# The APK is signed with apps/android/keystore (made on first build, kept out of git). Keep that file:
# Android only installs updates signed with the same key.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
SDK="${ANDROID_HOME:-$HOME/Library/Android/sdk}"
JAVA_HOME="${JAVA_HOME:-$HOME/Library/Java/jdk-17/Contents/Home}"
BT="$SDK/build-tools/35.0.0"
JAR="$SDK/platforms/android-35/android.jar"
KEYSTORE="${SL_KEYSTORE:-$ROOT/local/android/release.keystore}"
for f in "$BT/aapt2" "$BT/d8" "$JAR" "$JAVA_HOME/bin/javac"; do
  [ -e "$f" ] || { echo "Missing $f — see apps/android/README.md for the one-time setup."; exit 1; }
done
export JAVA_HOME PATH="$JAVA_HOME/bin:$PATH"

B="$(mktemp -d)"
trap 'rm -rf "$B"' EXIT
mkdir -p "$B/res" "$B/gen" "$B/classes" "$ROOT/dist"

echo "1/5 resources"
"$BT/aapt2" compile --dir "$HERE/res" -o "$B/res/res.zip"
"$BT/aapt2" link -I "$JAR" --manifest "$HERE/AndroidManifest.xml" -o "$B/app.unaligned.apk" \
  --java "$B/gen" --auto-add-overlay "$B/res/res.zip"

echo "2/5 compile"
# java.* comes from the JDK (Java 11 API, which Android 8+ covers for what this app uses), android.* from android.jar
javac -nowarn --release 11 -classpath "$JAR" -d "$B/classes" \
  $(find "$HERE/src" "$B/gen" -name "*.java")

echo "3/5 dex"
"$BT/d8" --release --min-api 26 --lib "$JAR" --output "$B" $(find "$B/classes" -name "*.class")
(cd "$B" && zip -q -u app.unaligned.apk classes.dex)

echo "4/5 align"
"$BT/zipalign" -f -p 4 "$B/app.unaligned.apk" "$B/app.aligned.apk"

echo "5/5 sign"
if [ ! -f "$KEYSTORE" ]; then
  mkdir -p "$(dirname "$KEYSTORE")"
  keytool -genkeypair -keystore "$KEYSTORE" -alias sourcelinga -keyalg RSA -keysize 3072 -validity 10000 \
    -storepass sourcelinga -keypass sourcelinga -dname "CN=Source Linga" >/dev/null 2>&1
  echo "   made a new signing key: $KEYSTORE (back it up)"
fi
"$BT/apksigner" sign --ks "$KEYSTORE" --ks-key-alias sourcelinga --ks-pass pass:sourcelinga \
  --key-pass pass:sourcelinga --out "$ROOT/dist/SourceLinga.apk" "$B/app.aligned.apk"
"$BT/apksigner" verify "$ROOT/dist/SourceLinga.apk"
echo "Built: $ROOT/dist/SourceLinga.apk ($(du -h "$ROOT/dist/SourceLinga.apk" | cut -f1))"
