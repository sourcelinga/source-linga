<p align="center"><img src="web/icon-180.png" width="96" alt="Source Linga logo"></p>

<h1 align="center">Source Linga</h1>
<p align="center"><b>Same Thing. Smarter Use. Better Output.</b><br>
A private AI that runs on your own Mac and finds better ways to use the tools, skills and workflows you already have.</p>

---

Source Linga runs entirely on your Mac: a local open model (through [Ollama](https://ollama.com)) plus a small Python engine called **Forge**. Nothing you type leaves the machine. You use it from a **native Mac app**, and your **iPhone, iPad, Android phone** and other Macs use the same AI over your home Wi-Fi, with your chats synced between them.

<p align="center">
<a href="https://github.com/sourcelinga/source-linga/releases/latest/download/SourceLinga.dmg"><b>⬇ Download for Mac</b></a> ·
<a href="https://github.com/sourcelinga/source-linga/releases/latest/download/SourceLinga.apk">Android app</a> ·
<a href="docs/INSTALL.md"><b>Step-by-step install guide</b></a>
</p>

| | App | What you get |
|---|---|---|
| **Mac** (macOS 14+) | Native SwiftUI app with Liquid Glass | One-click setup, chats synced with your phones, ⌥Space from any app, menu-bar quick ask, streamed answers with copy, read-aloud, share, retry and edit, and a built-in Tools window. |
| **iPhone / iPad** (iOS 17+) | Home Screen app, plus native SwiftUI source | Full-screen chat in one tap, with synced history, search, copy and read-aloud. |
| **Android** (8.0+) | Native app (0.2 MB APK) | Finds your Mac by itself, pairs with a 6-digit code, Share → Source Linga from any app, New-chat shortcut, dark mode. |

What makes it different from a plain local chatbot:

- **It improves your work, not just answers questions.** Give it a skill, prompt, email, workflow or script. It writes several versions with different strategies, scores them, checks the winner against your original twice (with the order swapped) and shows a diff.
- **It knows your material.** It indexes your notes and project files, and learns lessons from them.
- **It brings expert playbooks.** 12 skills adapted from popular open-source collections (debugging, testing, planning, copywriting, cold outreach, social posts and more). The best match is added to each request automatically.
- **It updates itself, carefully.** Once a week it tries one newer model and switches only if it scores higher on a fixed test suite. It rewrites its own instructions only when the tests improve. The judge is frozen, so it can't make its own grading easier.
- **It stays honest.** Your optional "house rules" (facts and forbidden claims) apply to every answer and every draft.

## Install (no Terminal, no account)

1. **Download** [SourceLinga.dmg](https://github.com/sourcelinga/source-linga/releases/latest/download/SourceLinga.dmg), open it and drag **Source Linga** into **Applications**.
2. **Open it.** The first time, macOS asks you to confirm: go to **System Settings → Privacy & Security → Open Anyway**.
3. Click **Set up on this Mac**. The app installs Ollama and the right-sized AI model for your Mac, plus a small background service, and shows each step as it goes. It takes 10–30 minutes, almost all of it the model download.
4. Click **Start chatting**.

Phones and other Macs: **Tools → Devices** on the Mac shows a QR code. Scan it and type the 6-digit code. Someone far away: tick **Share with someone far away** in the same tab and send them an **invite link**. They tap it and chat, with no app, account or code. The **[install guide](docs/INSTALL.md)** walks through every device, plus updating and uninstalling.

### Requirements

- A Mac with Apple silicon (M1 or newer) and macOS 14 Sonoma or newer.
- 8 GB of memory or more. Macs with 16 GB+ get `qwen3.5:9b`; 8 GB Macs get the lighter `qwen3.5:4b`, chosen automatically.
- About 12 GB of free disk space.

### From source (developers)

```bash
git clone https://github.com/sourcelinga/source-linga.git && cd source-linga && bash install.sh
```

## Make it yours (optional, 5 minutes)

The app setup keeps these files in `~/Library/Application Support/SourceLinga/engine` (in Finder: **Go → Go to Folder…**). A source install keeps them in the repository folder. Open them in TextEdit.

| File | What to put there |
|---|---|
| `house-rules.md` | Starts empty. Add `- ` lines with your facts (prices, policies, product details) and claims it must never make. |
| `config.json` | Created on first run from `config.example.json`. Set `sources` (folders to learn from) and `allowed_roots` (folders it may read). |
| `local/workflows/*.md` | Your own one-click business workflows (same format as `workflows/`). |
| `evals/local-cases.json` | Tests of your own facts (see `evals/local-cases.example.json`). Model switches and prompt rewrites must pass these. |
| `local/skills/<name>/SKILL.md` | Your own skills; a file with the same name overrides a shipped one. |

Everything above is listed in `.gitignore`, so it never gets published if you fork or push the repo.

## Using it

### On the Mac
Open the **Source Linga** app for chatting (⌘N new chat, ⌥Space from anywhere, menu-bar quick ask). Its 🛠 **Tools** window (or http://127.0.0.1:8777) has everything else:

| Tab | Use it for |
|---|---|
| **Chat** | Ask anything. Answers stream as they are written. It uses your notes, the best-matching skill, a calculator for every sum, and can read files in your allowed folders. |
| **Improve** | Load or paste a skill, prompt, email or script, say what should be better, and get ranked improved versions with a diff. **Apply** writes the winner back (a backup is kept). |
| **Workflows** | One-click drafts (outreach message, customer reply, product description, Instagram post, SEO title). |
| **Knowledge** | Search everything it knows; see the installed skills. |
| **Updates** | Model tests, auto-update history, strategy win-rates. |
| **Self-prompts** | Its own instructions, with every older version one click away. |
| **Devices** | Turn on iPhone/iPad access and see the pairing code; share with someone far away by invite link. |

### On iPhone, iPad, Android or another Mac (same Wi-Fi)
1. On the Mac: **Tools → Devices** → tick *Let my iPhone, iPad and other Macs on this Wi-Fi use Source Linga*. A QR code and a 6-digit pairing code appear.
2. Scan the QR code with the phone's camera and follow the page: **iPhone/iPad** pair and *Add to Home Screen*; **Android** download and install the app, which finds the Mac by itself.
3. Type the pairing code once per device.

Full step-by-step instructions, the native iPhone app, using it away from home, and fixes for common problems: **[docs/INSTALL.md](docs/INSTALL.md)**.

### Native apps, Siri and scripts
Source Linga speaks the Ollama and OpenAI APIs, so other apps get the same knowledge, skills and tools. Use the **app key** from the Devices tab.

- **[Enchanted](https://github.com/gluonfield/enchanted)** (free, iPhone/iPad/Mac): Settings → server URL `http://your-mac.local:8777/ollama`, Bearer token = app key, model `source-linga`.
- **Any OpenAI-compatible app:** base URL `http://your-mac.local:8777/v1`, API key = app key, model `source-linga`.
- **Siri / Shortcuts:** make a shortcut called *Ask Source Linga*: *Ask for Text* → *Get Contents of URL* (`…/v1/chat/completions`, POST, header `Authorization: Bearer <app key>`, JSON body `model: source-linga`, `messages: [{role: user, content: <Provided Input>}]`) → *Get Dictionary Value* `choices.1.message.content` → *Speak Text*.
- **curl:**
  ```bash
  curl http://127.0.0.1:8777/v1/chat/completions -H 'Content-Type: application/json' -d '{"model":"source-linga","messages":[{"role":"user","content":"Hello"}]}'
  ```

## Speed

A 9B model on a base M4 reads about 150 prompt tokens per second, so the waiting is mostly *reading*, not writing. Source Linga is built around that:

- The instructions never change between turns, so a follow-up question only reads the new part (≈2–8 s instead of 20 s+).
- Notes and the skill card are capped and added only to the newest message; tool descriptions are kept short.
- While you type in the web app and pause, it starts reading your draft; if you send that text, the answer starts almost instantly (measured 0.4 s).
- Answers stream word by word, the model is kept loaded for an hour, and background self-updates wait while you are chatting.

## How it improves itself

Run by the background service (`forge/updater.py`):

| Task | Every | What happens |
|---|---|---|
| knowledge | 6 h | Re-index files that changed. |
| lessons | day | Turn new Claude Code sessions into lessons (what worked, what failed, what you corrected). |
| model_updates | week | Re-pull the model if a newer build exists. |
| candidate_eval | week | Download **one** newer model that fits, run the test suite, switch only if it scores ≥ 5 points higher and is fast enough; delete the loser. |
| prompt_self_improve | week | Rewrite its own chat/draft instructions; keep a rewrite only if the tests improve. |

The tests (`evals/cases.json` + your `evals/local-cases.json`) are deterministic: string, regex, JSON, word-count and real Python checks. The model cannot talk its way to a better score.

## Privacy and security

- Models, index, chats and backups stay on your Mac (`data/`). It only goes online to download models and updates.
- With device access off, the server listens on `127.0.0.1` only. With it on, every request from another device needs the device key (pairing cookie or Bearer token); wrong pairing codes are rate-limited; the key and code are shown only on the Mac itself.
- Requests from other websites are refused (Origin/Host checks), so a web page you visit cannot drive it.
- Chat can read only inside `allowed_roots` and can write only to `outputs/`.
- **Sharing with someone far away** is off until you turn it on. It uses a free Cloudflare quick tunnel (Cloudflare's signed `cloudflared`, checked before it runs), so nothing is opened on your router. Only one-time invite links get in; guests can only chat and see only their own chats (no files, notes, house rules or tools), and the pairing code never works from the internet.

## Commands (source installs)

```bash
bash restart.sh
```
```bash
python3 -m forge.updater --force
```
```bash
python3 -m forge.updater candidate_eval --force
```

## Honest limits

A 9B local model is much weaker than the best cloud models. Source Linga's strength is that it is private, free to run all day, and disciplined: it tries many variations and keeps only what measurably scores better. Use a frontier model for the hardest problems.

## Credits

- Skills adapted (condensed, MIT) from [obra/superpowers](https://github.com/obra/superpowers) and [coreyhaines31/marketingskills](https://github.com/coreyhaines31/marketingskills); ideas from [muratcankoylan/Agent-Skills-for-Context-Engineering](https://github.com/muratcankoylan/Agent-Skills-for-Context-Engineering). See [skills/THIRD_PARTY_NOTICES.md](skills/THIRD_PARTY_NOTICES.md).
- Runs on [Ollama](https://ollama.com) and open models (default: Qwen 3.5 9B, nomic-embed-text).
- Works with [Enchanted](https://github.com/gluonfield/enchanted) on iPhone/iPad/Mac.
- QR codes by [qrcode-generator](https://github.com/kazuhikoarase/qrcode-generator) (Kazuhiko Arase, MIT).

## License

MIT for the Source Linga code (see [LICENSE](LICENSE)). The adapted skills keep their original MIT licenses.

<sub>Source Linga is an independent, non-commercial initiative. It is not affiliated with, sponsored by, or endorsed by any foundation, nor by Anthropic, Ollama, Alibaba (Qwen) or the authors of the adapted skills.</sub>
