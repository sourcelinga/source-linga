# Install Source Linga: step by step

No Terminal, no code, no account and no sign-in. You download one app, open it and click **Set up**.

Source Linga's AI runs on **one Mac**, your "AI Mac". Your iPhone, iPad, Android phone and other Macs use that Mac's AI over your home Wi-Fi.

| Device | What you install | Needs |
|---|---|---|
| **AI Mac** | The Source Linga app (it sets everything up itself) | Apple silicon (M1 or newer), macOS 14 Sonoma or newer, 8 GB memory (16 GB recommended), about 12 GB free |
| **iPhone / iPad** | Nothing from the App Store: a Home Screen app, added from Safari | iOS / iPadOS 17 or newer, same Wi-Fi |
| **Android** | The Source Linga app (APK, 0.2 MB) | Android 8.0 or newer, same Wi-Fi |
| **Other Macs** | The same Source Linga app | macOS 14 or newer, same Wi-Fi |

---

## Step 1: Download the Mac app

1. Open the **[latest release](https://github.com/sourcelinga/source-linga/releases/latest)**.
2. Under **Assets**, click **SourceLinga.dmg**. It is about 3 MB.
3. Open your **Downloads** folder and double-click **SourceLinga.dmg**.
4. In the window that opens, **drag the Source Linga icon onto the Applications folder**.
5. Close the window, then eject the disk image (click ⏏ next to *Source Linga* in a Finder sidebar).

## Step 2: Open it the first time

Source Linga is free and open source, but it isn't sold through Apple, so the first time macOS asks you to confirm.

1. Open **Applications** and double-click **Source Linga**.
2. macOS says *"Source Linga" Not Opened*. Click **Done**. (Don't click *Move to Bin*.)
3. Open  **Apple menu → System Settings → Privacy & Security**.
4. Scroll down to **Security**. Next to *"Source Linga" was blocked…*, click **Open Anyway**.
5. Type your Mac password (or use Touch ID), then click **Open Anyway** once more.

You only do this once. After that, Source Linga opens like any other app.

## Step 3: Click "Set up on this Mac"

The app opens on a welcome screen that checks your Mac (memory, chip and free space) and shows what it will download.

1. Click **Set up on this Mac**.
2. If macOS shows a window asking to install the **command line developer tools**, click **Install**, then **Agree**. This is Apple's free toolkit and provides the Python that Source Linga runs on. It takes 5–15 minutes. Source Linga waits and carries on by itself when it's done.
3. Source Linga now does the rest. You see each step tick off:
   - **Ollama, the AI runtime** (about 200 MB)
   - **The AI model**: `qwen3.5:9b` (about 7 GB) on Macs with 16 GB of memory or more, or the lighter `qwen3.5:4b` (about 3.7 GB) on 8 GB Macs. A progress bar shows the download. You can keep using your Mac.
   - **Background service**, so the AI is ready whenever you open the app
4. If macOS asks whether *Forge* may access your Documents folder, click **Allow**. If it says a **background item was added**, that's Source Linga's service. Leave it on.
5. When you see **Ready**, click **Start chatting**.

That's all. Everything now works **offline**, and nothing you type leaves your Mac.

> **Something went wrong?** Click **Try again**. Setup picks up where it stopped and doesn't download anything twice. **Show details** shows what happened, and **Copy details** copies it so you can paste it into an [issue](https://github.com/sourcelinga/source-linga/issues).

### Using Source Linga on the Mac

- **Chat:** your chats are on the left. **⌘N** starts a new chat, **Return** sends, **⌘.** stops an answer, **⌘R** tries again.
- **⌥Space** brings Source Linga forward from any app. You can turn this off in **Settings (⌘,)**.
- **Menu bar:** the capsule icon at the top of the screen opens a quick-ask box.
- **Answer buttons:** copy, read aloud, share, try again, edit your question.
- **Tools** (🛠 at the bottom of the chat list): *Improve* any prompt, email or document, one-click *Workflows*, *Knowledge*, *Updates* and *Devices*.

---

## Step 4 (optional): Your iPhone and iPad

### First, on the Mac
1. In Source Linga, click **🛠 Tools → Devices**.
2. Tick **Let my iPhone, iPad and other Macs on this Wi-Fi use Source Linga**.
3. A **QR code** and a **6-digit pairing code** appear. Keep this window open.
4. If macOS asks whether *Python* may accept incoming network connections, click **Allow**.

### Then, on the iPhone or iPad
1. Make sure it's on the **same Wi-Fi** as the Mac.
2. Open the **Camera** and point it at the QR code. Tap the link that appears.
3. Type the **6-digit code**, then tap **Pair**.
4. Tap **Share** (the square with an arrow) → **Add to Home Screen** → **Add**.
5. Open **Source Linga** from your Home Screen. It opens full screen, like any app.

> Use **Safari** for steps 2–4. Other iPhone browsers can't add a full-screen app to the Home Screen.

---

## Step 5 (optional): Your Android phone

1. Turn on device access on the Mac (see *First, on the Mac* above).
2. On the phone, scan the QR code with the **Camera** or **Google Lens** and open the link in **Chrome**. *Or* download **SourceLinga.apk** from the [latest release](https://github.com/sourcelinga/source-linga/releases/latest).
3. Tap **Download the Android app**, then **Open** when it finishes.
4. If Android says Chrome isn't allowed to install apps: tap **Settings**, turn on **Allow from this source**, then go back.
5. Tap **Install**. If Play Protect asks, tap **More details → Install anyway** (the app isn't on the Play Store).
6. Open **Source Linga**, tap your Mac in the list and type the **6-digit code**.

Extras: **Share → Source Linga** from any app starts a chat with the shared text, and a long press on the icon gives a **New chat** shortcut.

---

## Another Mac in the house

1. Do **Step 1** and **Step 2** on the other Mac.
2. On the welcome screen, click **Use the AI on another Mac**.
3. Click your AI Mac in the list and type the **6-digit code** from its **Tools → Devices**.

---

## Someone far away (optional)

Let a friend, family member or colleague in another city use the AI on your Mac. They need **no app, no account and no pairing code**, only a link from you.

### On your Mac
1. In Source Linga, click **🛠 Tools → Devices**.
2. Tick **Share with someone far away** and click **OK**. The first time, Source Linga downloads Cloudflare's free connector (about 40 MB). After a few seconds an **Address** appears.
3. Type the person's name and click **Create invite link**.
4. Click **Copy link** (or scan the QR code) and send it to them by WhatsApp, iMessage or email.

### On their phone or computer
1. Open the link.
2. Tap **Accept invite**, then **Start chatting**.
3. To keep it one tap away: **iPhone/iPad** Share → *Add to Home Screen*; **Android** ⋮ → *Add to Home screen*; **computer** bookmark it.

### Good to know
- **Private by design.** Each link works **once**, for one person, within 7 days. Invited people can only chat, and only see their own chats. They never see your files, notes, house rules, chats, tools or pairing code. Nobody can sign in with the 6-digit code from the internet.
- **Your Mac does the work.** It must be on, awake and online. While sharing is on, Source Linga keeps it from going to sleep by itself (closing a laptop's lid still sleeps it).
- **If the address changes.** If your Mac restarts or you turn sharing off and on, the address changes. Click **New link** next to the person and send it again; their chats are kept.
- **Remove someone** with **Remove**. Their access stops at once and their chats are deleted.

> Prefer a permanent private network instead? The free **[Tailscale](https://tailscale.com)** app works too: install it on both devices, share your Mac with the other person from Tailscale's admin page, and in the phone app use **Change Mac** with the Mac's `100.x.y.z` address.

---

## Updating

Download the newest **SourceLinga.dmg** and drag the app into Applications again (choose **Replace**). Open it and, if it asks, click **Set up on this Mac**. Setup keeps your chats, settings and models, so it only takes a minute. The AI model updates itself: once a week Source Linga tests one newer model and switches only if it scores better.

## Uninstalling

1. Open Source Linga → **Settings (⌘,)** → **Remove the AI engine from this Mac…** → **Remove**.
2. Drag **Source Linga** from Applications to the Bin.
3. Optional, to free the disk space: drag **Ollama** from Applications to the Bin, and delete the folder **~/.ollama** (in Finder: **Go → Go to Folder…**, type `~/.ollama`).

---

## Troubleshooting

| Problem | Fix |
|---|---|
| *"Source Linga" Not Opened* / *Apple could not verify…* | Do **Step 2**: System Settings → Privacy & Security → **Open Anyway**. |
| Setup waits at **Apple developer tools** | Look for the macOS *Install* window (it may be behind other windows). If you closed it, click **I've installed them**, and setup asks again. |
| The model download is slow or stops | Click **Try again**. Downloads continue where they stopped. |
| *Set up* is greyed out | There isn't enough free disk space. Free up at least 12 GB and reopen the app. |
| The phone says *Can't reach your Mac* | Check that the Mac is awake, the phone is on the same Wi-Fi (not mobile data), and **Tools → Devices** access is on. |
| The Mac isn't in the phone's list | Type the address shown in **Tools → Devices**. Guest Wi-Fi networks often block devices from seeing each other. |
| *Wrong code* | Codes are 6 digits. After 5 wrong tries, wait 10 minutes. |
| The first answer is slow | The model is loading into memory (10–20 s). Later answers start in a few seconds. |
| An invite link says *already used or expired* | Each link works once, within 7 days. On the Mac, click **New link** next to the person and send it again. |
| A far-away person sees *Can't reach the Mac* | The Mac is asleep, off or offline, or sharing was turned off. |
| *The AI engine is off* | Click **Start engine** in the banner, or **Settings → Start the AI engine**. |

---

## For developers

Everything above uses the app. If you prefer the source:

```bash
git clone https://github.com/sourcelinga/source-linga.git && cd source-linga && bash install.sh
```

- **Mac app:** `bash apps/mac/build.sh --install` (needs only the Command Line Tools; the build carries the engine inside the app).
- **Android app:** `bash apps/android/build.sh` (see [apps/android/README.md](../apps/android/README.md); no Android Studio or Gradle).
- **Native iPhone/iPad app:** open `apps/apple/SourceLinga.swiftpm` in Xcode or Swift Playgrounds and press Run (see [apps/apple/README.md](../apps/apple/README.md)).
