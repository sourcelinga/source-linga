import SwiftUI
#if os(macOS)
import AppKit
#else
import UIKit
#endif

@main
struct SourceLingaApp: App {
    @State private var store = ChatStore()
    #if os(macOS)
    @State private var quick = ChatStore()
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var delegate
    #endif

    var body: some Scene {
        #if os(macOS)
        Window("Source Linga", id: "main") {
            RootView().environment(store)
                .frame(minWidth: 640, minHeight: 460)
                .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
                    Task { await store.refresh() }
                }
        }
        .defaultSize(width: 1080, height: 760)
        .commands { chatCommands }

        Window("Tools", id: "tools") {
            if let base = store.toolsURL {
                WebTools(base: base, key: store.endpoint?.key).frame(minWidth: 800, minHeight: 560)
            }
        }
        .defaultSize(width: 1180, height: 800)

        MenuBarExtra {
            QuickAskView().environment(quick).environment(\.mainStore, store)
        } label: {
            MenuBarIcon()
        }
        .menuBarExtraStyle(.window)

        Settings { SettingsView().environment(store) }
        #else
        WindowGroup {
            RootView().environment(store)
                .onReceive(NotificationCenter.default.publisher(for: UIApplication.didBecomeActiveNotification)) { _ in
                    Task { await store.refresh() }
                }
        }
        .commands { chatCommands }
        #endif
    }

    private var chatCommands: some Commands {
        Group {
            CommandGroup(replacing: .newItem) {
                Button("New Chat") { store.newChat() }.keyboardShortcut("n")
            }
            CommandMenu("Chat") {
                Button("Stop Answer") { store.stop() }.keyboardShortcut(".").disabled(!store.isStreaming)
                Button("Try Again") { store.retry() }.keyboardShortcut("r")
                Button("Edit Last Question") { store.editLast() }.keyboardShortcut("e")
            }
        }
    }
}

#if os(macOS)
final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ n: Notification) {
        if UserDefaults.standard.object(forKey: "hotkey") as? Bool ?? true { HotKey.shared.register() }
        HotKey.shared.action = { AppDelegate.showMain() }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ app: NSApplication) -> Bool { false }  // stays in the menu bar

    static var openMain: (() -> Void)?

    static func showMain() {
        NSApp.activate(ignoringOtherApps: true)
        if let w = NSApp.windows.first(where: { $0.identifier?.rawValue == "main" }), w.isVisible {
            w.makeKeyAndOrderFront(nil)
        } else {
            openMain?()
        }
        NotificationCenter.default.post(name: .slFocusComposer, object: nil)
    }
}

extension Notification.Name { static let slFocusComposer = Notification.Name("slFocusComposer") }

private struct MainStoreKey: EnvironmentKey { static let defaultValue: ChatStore? = nil }
extension EnvironmentValues {
    var mainStore: ChatStore? {
        get { self[MainStoreKey.self] }
        set { self[MainStoreKey.self] = newValue }
    }
}

/// The menu bar icon. It is always alive, so it also hands the app a way to reopen the main window.
struct MenuBarIcon: View {
    @Environment(\.openWindow) private var openWindow
    var body: some View {
        Image(systemName: "capsule.portrait")
            .onAppear { AppDelegate.openMain = { openWindow(id: "main") } }
    }
}

/// Quick ask from the menu bar: one question, one streamed answer, without leaving what you are doing.
struct QuickAskView: View {
    @Environment(ChatStore.self) private var quick
    @Environment(\.mainStore) private var main
    @Environment(\.openWindow) private var openWindow
    @FocusState private var focused: Bool

    var body: some View {
        @Bindable var quick = quick
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 10) {
                Logo(size: 24)
                Text("Source Linga").font(.headline)
                StatusDot(connection: quick.connection)
                Spacer()
                Button { quick.newChat() } label: { Image(systemName: "square.and.pencil") }
                    .buttonStyle(.borderless).help("New question")
                Button { AppDelegate.openMain = { openWindow(id: "main") }; AppDelegate.showMain() } label: {
                    Image(systemName: "macwindow")
                }
                .buttonStyle(.borderless).help("Open the full app")
            }
            if let answer = quick.current.messages.last(where: { !$0.isUser }) {
                ScrollView {
                    VStack(alignment: .leading, spacing: 8) {
                        if let q = quick.current.messages.last(where: { $0.isUser }) {
                            Text(q.content).font(.callout).foregroundStyle(.secondary).lineLimit(3)
                        }
                        if let e = answer.error { Label(e, systemImage: "exclamationmark.triangle").foregroundStyle(.red) }
                        else if answer.content.isEmpty { HStack { PulseOrb(); Text(answer.status ?? "Thinking…").foregroundStyle(.secondary) } }
                        else { MarkdownView(text: answer.content, streaming: answer.streaming) }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
                .frame(maxHeight: 380)
                .defaultScrollAnchor(.bottom)
                if !answer.streaming && !answer.content.isEmpty {
                    HStack {
                        Button("Copy", systemImage: "doc.on.doc") { Clipboard.copy(answer.content) }
                        Button("Continue in app", systemImage: "arrow.up.forward.app") {
                            main?.open(quick.current.id)
                            AppDelegate.openMain = { openWindow(id: "main") }
                            AppDelegate.showMain()
                        }
                    }
                    .buttonStyle(.borderless).font(.callout)
                }
            }
            HStack(alignment: .bottom, spacing: 8) {
                TextField("Ask anything…", text: $quick.draft, axis: .vertical)
                    .textFieldStyle(.plain).lineLimit(1...6).focused($focused)
                    .onSubmit { quick.send() }
                    .onChange(of: quick.draft) { quick.draftChanged() }
                Button { quick.isStreaming ? quick.stop() : quick.send() } label: {
                    Image(systemName: quick.isStreaming ? "stop.circle.fill" : "arrow.up.circle.fill").font(.title2)
                        .foregroundStyle(Theme.accent)
                }
                .buttonStyle(.borderless)
            }
            .padding(10)
            .glassCard(18)
        }
        .padding(14)
        .frame(width: 420)
        .task { await quick.refresh(); focused = true }
    }
}
#endif
