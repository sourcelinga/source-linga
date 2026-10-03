<p align="center"><img src="web/icon-180.png" width="96" alt="Source Linga logo"></p>

<h1 align="center">Source Linga</h1>
<p align="center"><b>Same Thing. Smarter Use. Better Output.</b><br>
A private AI that runs on your own Mac and finds better ways to use the tools, skills and workflows you already have.</p>

---

Source Linga runs entirely on your Mac: a local open model (through [Ollama](https://ollama.com)) plus a small Python engine called **Forge**. Nothing you type leaves the machine. You use it from a **native Mac app**, and your **iPhone, iPad, Android phone** and other Macs use the same AI over your home Wi-Fi, with your chats synced between them.

<p align="center"><b>📱 <a href="docs/INSTALL.md">Step-by-step install for Mac, iPhone, iPad and Android →</a></b><br>
<a href="https://github.com/sourcelinga/source-linga/releases/latest">Download the apps (Releases)</a></p>

| | App | What you get |
|---|---|---|
| **Mac** (macOS 14+) | Native SwiftUI app | Chat list synced with your phones; ⌥Space from any app; menu-bar quick ask; streamed Markdown answers with copy, read-aloud, share, retry and edit; built-in Tools window. |
| **iPhone / iPad** (iOS 17+) | Home Screen app, plus native SwiftUI source | Full-screen chat in one tap: synced history, search, copy, read-aloud, and the keyboard never covers the composer. Optional native app via Xcode. |
| **Android** (8.0+) | Native app (300 KB APK) | Finds your Mac by itself, pairs with a 6-digit code, Share → Source Linga from any app, New-chat shortcut, dark mode. |

What makes it different from a plain local chatbot:

- **It improves your work, not just answers questions.** Give it a skill, prompt, email, workflow or script; it writes several versions using different strategies, scores them, checks the winner against the original twice (order swapped) and shows a diff.
- **It knows your material.** It indexes your notes, skills, project files and past Claude Code sessions, and learns lessons from them.
- **It brings expert playbooks.** 12 skills adapted from popular open-source collections (debugging, testing, planning, copywriting, cold outreach, social posts and more). The best match is added to each request automatically.
- **It updates itself, carefully.** Weekly it tries one newer model and switches only if it scores higher on a fixed test suite; it rewrites its own instructions only when the tests improve. The judge is frozen, so it can't grade itself easier.
- **It stays honest.** Your "house rules" (facts and forbidden claims) are enforced on every answer and every draft.

## Requirements

- A Mac with Apple Silicon (M1 or newer). 16 GB RAM recommended for the default 9B model.
- macOS 14 Sonoma or newer, ~10 GB free disk.
- Python 3 (the one that comes with the Xcode Command Line Tools is enough; no extra packages).

## Install

```bash
git clone https://github.com/sourcelinga/source-linga.git
```
```bash
cd source-linga && bash install.sh
```

The installer downloads Ollama (if missing) and the models (`qwen3.5:9b`, ~6.6 GB, and `nomic-embed-text`), then installs a small background service (`~/Applications/Forge.app`) that starts at login. If macOS asks whether it may read your Documents folder, click **Allow**.

Then open **Source Linga** from Launchpad or `~/Applications` (the installer builds the Mac app), or open **http://127.0.0.1:8777/app** in a browser. The full tools are at **http://127.0.0.1:8777**.

To stop and remove the service later: `bash uninstall.sh` (your models and data stay).

## Make it yours (5 minutes)

| File | What to put there |
|---|---|
| `house-rules.md` | Copy `house-rules.example.md`. Your facts (prices, policies, product details) and claims it must never make. |
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
| **Devices** | Turn on iPhone/iPad access and see the pairing code. |

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

## Commands

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
