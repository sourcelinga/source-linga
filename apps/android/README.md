# Source Linga for Android

A native Android app (Java, no AndroidX, 300 KB) for Android 8.0 and newer. It finds the AI Mac on the Wi-Fi with Bonjour (`_sourcelinga._tcp`) and pairs using the Mac's 6-digit code. It then shows the chat app the Mac serves (`/app`) and adds native features:

- Copy, share and read aloud.
- Haptics.
- *Share → Source Linga* from any app.
- A *New chat* launcher shortcut.
- Edge-to-edge layout that keeps clear of the keyboard.
- A screen for when the Mac is offline.

To install it on a phone, see [docs/INSTALL.md](../../docs/INSTALL.md#3-android).

## Build it (no Android Studio, no Gradle)

One-time setup (about 1 GB):

1. Install JDK 17 (for example [Temurin](https://adoptium.net)).
2. Install the [Android command-line tools](https://developer.android.com/studio#command-line-tools-only).
3. Install the SDK packages:

```bash
sdkmanager "platforms;android-35" "build-tools;35.0.0" "platform-tools"
```

Then build:

```bash
ANDROID_HOME=~/Library/Android/sdk JAVA_HOME=/path/to/jdk-17 bash apps/android/build.sh
```

The build writes `dist/SourceLinga.apk`, which your Mac also offers to phones at `http://<your-mac>:8777/get`. To install it on a phone connected with USB debugging:

```bash
adb install -r dist/SourceLinga.apk
```

The first build makes a signing key at `local/android/release.keystore`, which is never published. Back it up: Android installs updates only when they are signed with the same key.

## Files

- `AndroidManifest.xml`: permissions (internet and Wi-Fi multicast for discovery only), the share targets and cleartext HTTP to your own Mac.
- `src/com/sourcelinga/app/MainActivity.java`: discovery, pairing, the WebView and the `SLNative` bridge used by `web/app.html`.
- `res/`: the layout, the light and dark theme, and the icons (adaptive and monochrome).
