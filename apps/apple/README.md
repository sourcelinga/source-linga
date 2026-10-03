# Source Linga for Mac, iPhone and iPad (SwiftUI)

The Mac app and the iPhone/iPad app are built from one set of SwiftUI files in `SourceLinga.swiftpm/Sources/App`.

| File | What it does |
|---|---|
| `API.swift` | Talks to the engine: streamed answers, synced chats and pairing. Also finds Macs with Bonjour and keeps the device key in the Keychain. |
| `ChatStore.swift` | Holds the app's state: chats, streaming, stop, retry, edit, read-ahead and read-aloud. |
| `ChatViews.swift` | The chat list, the conversation, Markdown answers, the composer and the empty state. |
| `ConnectViews.swift` | The *Connect to your Mac* pairing screen and Settings. |
| `Markdown.swift` | Renders answers: headings, lists, quotes and code blocks with a Copy button. |
| `Platform.swift` | Mac- and iPhone-specific parts: clipboard, web tools, the ⌥Space hot key and starting the engine. |
| `SourceLingaApp.swift` | The windows, the menu-bar quick ask and the keyboard commands. |

- **Mac:** `bash apps/mac/build.sh --install` needs only Apple's Command Line Tools. It builds a universal app for macOS 14 and newer.
- **iPhone / iPad:** open `SourceLinga.swiftpm` in Xcode 15+ (or Swift Playgrounds on iPad), choose your device and press Run. For step-by-step instructions, see [docs/INSTALL.md](../../docs/INSTALL.md#the-native-iphone-app-optional-needs-xcode).
