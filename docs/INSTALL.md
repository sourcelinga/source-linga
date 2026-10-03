# Install Source Linga on every device

Source Linga's AI runs on **one Mac**, the "AI Mac". Your other devices use that Mac's AI over Wi-Fi:

| Device | App | Needs |
|---|---|---|
| **AI Mac** | Engine + native Mac app | Apple silicon (M1 or newer), macOS 14 Sonoma or newer, 16 GB RAM recommended, ~10 GB free |
| **iPhone / iPad** | Home Screen app (native app optional) | iOS / iPadOS 17 or newer, same Wi-Fi as the AI Mac |
| **Android phone / tablet** | Native app (APK) | Android 8.0 or newer, same Wi-Fi as the AI Mac |
| **Other Macs** | Native Mac app | macOS 14 or newer (Intel or Apple silicon), same Wi-Fi |

Chats are saved on the AI Mac and show up on every device you pair.

Downloads for the latest version are on the [Releases page](https://github.com/sourcelinga/source-linga/releases/latest).

---

## 1. The AI Mac (do this first)

1. Open **Terminal** (press ⌘Space, type *Terminal*, press Return).
2. If you have never used developer tools on this Mac, install Apple's free Command Line Tools and click **Install** in the window that opens:
   ```bash
   xcode-select --install
   ```
3. Download Source Linga:
   ```bash
   git clone https://github.com/sourcelinga/source-linga.git ~/source-linga
   ```
4. Run the installer. It takes 10–30 minutes, mostly to download the AI model (~7 GB):
   ```bash
   cd ~/source-linga && bash install.sh
   ```
   - The installer sets up Ollama, the models, a background service that starts at login, and the **Source Linga** Mac app.
   - If macOS asks whether *Forge* may access your Documents folder, click **Allow**.
5. Open **Source Linga** from Launchpad, Spotlight (⌘Space, type *Source Linga*) or `~/Applications`, then drag its Dock icon where you want it.

**Using the Mac app**

- **Chat:** your chats are listed on the left. Press **⌘N** for a new chat, **Return** to send, **⌘.** to stop an answer, **⌘R** to try again.
- **⌥Space** from any app brings Source Linga to the front, ready to type. You can switch this off in Settings.
- **Menu bar:** the capsule icon in the menu bar opens a quick-ask box for one-off questions.
- **Tools:** the 🛠 button at the bottom of the chat list opens Improve, Workflows, Knowledge, Updates and Devices.
- **Answer buttons:** under each answer you can copy it, have it read aloud, share it, try again, or edit your question.

> No Mac app? The same chat also runs in any browser at <http://127.0.0.1:8777/app>.

### Turn on access for your other devices

1. In the Mac app, click **🛠 Tools → Devices**.
2. Tick **Let my iPhone, iPad and other Macs on this Wi-Fi use Source Linga**. The engine restarts in about 5 seconds.
3. The page now shows a **QR code**, a **6-digit pairing code** and the Mac's **Wi-Fi address**. Keep it open while you set up your other devices.
4. If macOS asks whether *Python* may accept incoming network connections, click **Allow**.

---

## 2. iPhone and iPad

### The Home Screen app (no developer account needed)

1. Connect the iPhone to the **same Wi-Fi** as the AI Mac.
2. Open the **Camera** app and point it at the QR code in **Tools → Devices** on the Mac. Tap the yellow link.
   - *Or* open **Safari** and type the address shown on the Mac, followed by `/get`, for example `http://your-mac.local:8777/get`.
3. Tap **pair**, type the **6-digit code** shown on the Mac, then tap **Pair**.
4. Tap the **Share** button (the square with the arrow), scroll down, tap **Add to Home Screen**, then **Add**.
5. Open **Source Linga** from your Home Screen. It runs full screen like any other app, with your chat list, copy, read-aloud, try-again and edit buttons.

> Use **Safari** for steps 2–4. Other browsers on iPhone can't add a full-screen app to the Home Screen.

### The native iPhone app (optional, needs Xcode)

The repository also contains a native SwiftUI app for iPhone and iPad in `apps/apple/SourceLinga.swiftpm`. It adds automatic discovery of the Mac, Keychain storage of the key and native sharing. Apple only lets you install your own apps through Xcode:

1. On a Mac, install **Xcode** from the App Store (free, about 8 GB) and open it once.
2. In Finder, open `source-linga/apps/apple/` and double-click **SourceLinga.swiftpm**. Xcode opens it.
3. **Xcode → Settings → Accounts →** click **+** and sign in with your Apple ID. A free account is enough.
4. Plug the iPhone in with a cable and tap **Trust** on the phone. If asked, turn on **Settings → Privacy & Security → Developer Mode** on the iPhone and restart it.
5. In Xcode's toolbar, pick your iPhone as the destination. In the project's **Signing & Capabilities**, choose your Apple ID team.
6. Press **▶ Run**. The first time, go to **Settings → General → VPN & Device Management** on the iPhone and trust your Apple ID.
7. Open the app, tap your Mac in the list, then type the pairing code.

With a free Apple ID the app stops opening after 7 days; press **▶ Run** again in Xcode to renew it. A paid Apple Developer account removes this limit.

On an iPad you can also open `SourceLinga.swiftpm` in Apple's free **Swift Playgrounds** app and press **Run**.

---

## 3. Android

1. Connect the phone to the **same Wi-Fi** as the AI Mac.
2. Scan the QR code in **Tools → Devices** on the Mac with the camera or Google Lens, and open the link in **Chrome**.
   - *Or* type the address shown on the Mac followed by `/get` into Chrome, for example `http://192.168.1.20:8777/get`.
   - *Or* download **SourceLinga.apk** from the [Releases page](https://github.com/sourcelinga/source-linga/releases/latest).
3. Tap **Download the Android app**. When it finishes, tap **Open** in the notification, or find **SourceLinga.apk** in **Files → Downloads**.
4. Android may say the browser isn't allowed to install apps. Tap **Settings**, turn on **Allow from this source**, then go back.
5. Tap **Install**. If Google Play Protect asks about an unknown app, tap **More details → Install anyway**. The app isn't on the Play Store; it's the open-source app from this repository.
6. Open **Source Linga**. Under *Macs on this Wi-Fi*, tap your Mac, then type the **6-digit code**. That's it.
   - If your Mac isn't listed after a few seconds, type the address shown on the Mac (for example `192.168.1.20`) and tap **Next**.

What the Android app adds:
- **Share to Source Linga:** in any app, select text or tap **Share → Source Linga** to start a chat with it.
- **New chat shortcut:** long-press the app icon for a *New chat* shortcut.
- **Phone features:** copy, share, read aloud and haptics.
- **Change Mac:** use *Change Mac / settings* in the side menu.

---

## 4. Another Mac

1. On the other Mac, open the AI Mac's address followed by `/get` in Safari, for example `http://your-mac.local:8777/get`, and click **Download the Mac app**. You can also download **SourceLinga-mac.zip** from the [Releases page](https://github.com/sourcelinga/source-linga/releases/latest).
2. Double-click the zip, then drag **Source Linga** into **Applications**.
3. Open it. The app isn't notarized by Apple, so the first time macOS says it can't verify it:
   - Click **Done**, then open **System Settings → Privacy & Security**.
   - Scroll down to the message about Source Linga and click **Open Anyway**. Enter your password if asked.
4. The app opens on **Connect to your Mac**. Click the AI Mac in the list (or type its address), then type the pairing code. If macOS asks whether Source Linga may find devices on your local network, click **Allow**.
   - Later you can switch Macs in **Source Linga → Settings… (⌘,)**.

> If you build the app yourself with `bash apps/mac/build.sh --install`, macOS trusts it right away and step 3 isn't needed.

---

## 5. Away from home (optional)

Pairing works on your home Wi-Fi. To reach the AI Mac from anywhere, install the free **[Tailscale](https://tailscale.com)** on the AI Mac and on your phone, and sign in to both with the same account. In the phone app, use **Change Mac**, then type the Mac's Tailscale IP address (it starts with `100.`). Everything stays encrypted, and the AI still runs only on your Mac.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Phone says *Can't reach your Mac* | Check that the Mac is awake (not asleep with the lid closed), that the phone is on the same Wi-Fi rather than mobile data, and that **Tools → Devices** access is on. |
| The Mac isn't in the phone's list | Type the address shown in **Tools → Devices** instead. Some routers block device discovery ("AP/client isolation"); guest Wi-Fi networks usually do. |
| *Wrong code* | Codes are 6 digits and stay the same until you press **New key**. After 5 wrong tries, wait 10 minutes. |
| The app asks to pair again | Someone pressed **New key** on the Mac, which un-pairs every device. Pair again with the new code. |
| Mac app: *Apple could not verify…* | See step 3 of *Another Mac*, or run `xattr -dr com.apple.quarantine "/Applications/Source Linga.app"`. |
| The first answer is slow | The model is loading (about 10–20 s). Later answers start in 2–8 s. |
| The AI engine is off | In the Mac app, click **Start engine**, or run `bash restart.sh` in the source-linga folder. |

---

## Building the apps yourself

- **Mac app:**
  ```bash
  bash apps/mac/build.sh --install
  ```
  This needs only the Command Line Tools. It builds a universal app (Apple silicon and Intel) into `dist/` and copies it to `~/Applications`.
- **Android app:** `bash apps/android/build.sh`. See [apps/android/README.md](../apps/android/README.md) for the one-time JDK and SDK setup. It doesn't need Android Studio or Gradle.
- **iPhone app:** open `apps/apple/SourceLinga.swiftpm` in Xcode (see above).

Built apps are written to `dist/`, and the Mac serves them to your phones at `/get`.
