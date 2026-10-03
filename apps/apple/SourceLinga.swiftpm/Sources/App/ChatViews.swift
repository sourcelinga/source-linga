import SwiftUI

// MARK: - Window layout: chats on the left, the open chat on the right (a stack on iPhone)

struct RootView: View {
    @Environment(ChatStore.self) private var store
    @State private var columns: NavigationSplitViewVisibility = .automatic
    @State private var showTools = false
    @State private var showSettings = false

    /// iPhone/iPad before pairing, or a Mac without its own AI engine: show the "find your Mac" screen.
    private var needsConnect: Bool {
        if store.connection == .unpaired && !(store.endpoint?.isLocal ?? false) { return true }
        #if os(macOS)
        if store.endpoint?.isLocal == true, case .offline = store.connection, Engine.appURL == nil { return true }
        #endif
        return false
    }

    var body: some View {
        Group {
            if needsConnect {
                ConnectView()
            } else {
                NavigationSplitView(columnVisibility: $columns) {
                    Sidebar(showTools: $showTools, showSettings: $showSettings)
                        .navigationSplitViewColumnWidth(min: 220, ideal: 270, max: 360)
                } detail: {
                    ChatView()
                }
            }
        }
        .task { await store.refresh() }
        #if os(iOS)
        .sheet(isPresented: $showTools) {
            NavigationStack {
                if let base = store.toolsURL {
                    WebTools(base: base, key: store.endpoint?.key)
                        .ignoresSafeArea(edges: .bottom)
                        .navigationTitle("Tools").navigationBarTitleDisplayMode(.inline)
                        .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { showTools = false } } }
                }
            }
        }
        .sheet(isPresented: $showSettings) { NavigationStack { SettingsView() } }
        #endif
    }
}

struct Sidebar: View {
    @Environment(ChatStore.self) private var store
    @Binding var showTools: Bool
    @Binding var showSettings: Bool
    @State private var query = ""
    #if os(macOS)
    @Environment(\.openWindow) private var openWindow
    #endif

    private var groups: [(String, [ConvoSummary])] {
        let q = query.lowercased()
        let items = store.convos.filter { q.isEmpty || ($0.title + " " + ($0.preview ?? "")).lowercased().contains(q) }
        var out: [(String, [ConvoSummary])] = []
        for c in items {
            let g = Self.group(c.updated)
            if out.last?.0 == g { out[out.count - 1].1.append(c) } else { out.append((g, [c])) }
        }
        return out
    }

    static func group(_ t: Double) -> String {
        let cal = Calendar.current
        let d = Date(timeIntervalSince1970: t)
        let days = cal.dateComponents([.day], from: cal.startOfDay(for: d), to: cal.startOfDay(for: .now)).day ?? 0
        switch days {
        case ..<1: return "Today"
        case 1: return "Yesterday"
        case 2..<7: return "Previous 7 days"
        case 7..<30: return "Previous 30 days"
        default: return d.formatted(.dateTime.month(.wide).year())
        }
    }

    var body: some View {
        @Bindable var store = store
        List(selection: Binding(get: { store.selection }, set: { if let id = $0 { store.open(id) } })) {
            if store.convos.isEmpty {
                Text("Your chats appear here, on every device.")
                    .font(.callout).foregroundStyle(.secondary).listRowSeparator(.hidden)
            }
            ForEach(groups, id: \.0) { group, items in
                Section(group) {
                    ForEach(items) { c in
                        Text(c.title).lineLimit(1).tag(c.id)
                            .contextMenu { Button("Delete", systemImage: "trash", role: .destructive) { store.delete(c.id) } }
                            .swipeActions { Button("Delete", systemImage: "trash", role: .destructive) { store.delete(c.id) } }
                    }
                }
            }
        }
        .searchable(text: $query, placement: .sidebar, prompt: "Search chats")
        .refreshable { await store.refresh() }
        .navigationTitle("Source Linga")
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button { store.newChat() } label: { Label("New chat", systemImage: "square.and.pencil") }
                    .keyboardShortcut("n", modifiers: .command)
            }
            #if os(iOS)
            ToolbarItem(placement: .topBarLeading) {
                Menu {
                    Button("Tools: improve, workflows, knowledge", systemImage: "wrench.and.screwdriver") { showTools = true }
                    Button("Settings", systemImage: "gearshape") { showSettings = true }
                } label: { Label("More", systemImage: "ellipsis.circle") }
            }
            #endif
        }
        .safeAreaInset(edge: .bottom) {
            HStack(spacing: 8) {
                StatusDot(connection: store.connection)
                Text(store.statusLine).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                Spacer()
                #if os(macOS)
                Button { openWindow(id: "tools") } label: { Image(systemName: "wrench.and.screwdriver") }
                    .buttonStyle(.borderless).help("Tools: improve, workflows, knowledge, updates, devices")
                #endif
            }
            .padding(.horizontal, 14).padding(.vertical, 10)
            .background(.bar)
        }
    }
}

struct StatusDot: View {
    let connection: Connection
    var body: some View {
        Circle().fill(color).frame(width: 7, height: 7).shadow(color: color.opacity(0.7), radius: 3)
    }
    private var color: Color {
        switch connection {
        case .online: return .green
        case .connecting, .engineStarting: return .orange
        default: return .red
        }
    }
}

// MARK: - The conversation

struct ChatView: View {
    @Environment(ChatStore.self) private var store

    var body: some View {
        ScrollViewReader { proxy in
          GeometryReader { geo in
            ScrollView {
                if store.current.messages.isEmpty {
                    EmptyState().frame(maxWidth: .infinity).padding(.top, 40)
                } else {
                    LazyVStack(alignment: .leading, spacing: 22) {
                        ForEach(Array(store.current.messages.enumerated()), id: \.element.id) { i, m in
                            MessageRow(message: m, isLast: i == store.current.messages.count - 1).id(m.id)
                        }
                        Color.clear.frame(height: 1).id("bottom")
                    }
                    .frame(maxWidth: 760)
                    .padding(.horizontal, 18).padding(.vertical, 16)
                    .frame(maxWidth: .infinity, minHeight: geo.size.height, alignment: .top)  // short chats start at the top
                }
            }
            .defaultScrollAnchor(.bottom)
            .scrollDismissesKeyboard(.interactively)
            .onChange(of: store.current.messages.count) { withAnimation(.easeOut(duration: 0.2)) { proxy.scrollTo("bottom") } }
            .onChange(of: store.current.id) { proxy.scrollTo("bottom") }
          }
        }
        .safeAreaInset(edge: .bottom) { Composer() }
        .navigationTitle(store.current.messages.isEmpty ? "" : (store.current.title.isEmpty ? "New chat" : store.current.title))
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button { store.newChat() } label: { Label("New chat", systemImage: "square.and.pencil") }
            }
        }
        #endif
        .overlay(alignment: .top) {
            if case .offline(let why) = store.connection {
                Banner(text: why) { Task { await store.refresh() } }.padding(.top, 8)
            } else if store.connection == .engineStarting {
                Banner(text: "The AI engine on your Mac is starting…") { Task { await store.refresh() } }.padding(.top, 8)
            }
        }
    }
}

struct Banner: View {
    let text: String
    let retry: () -> Void
    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: "wifi.exclamationmark")
            Text(text).font(.callout).lineLimit(2)
            Spacer(minLength: 4)
            #if os(macOS)
            if Engine.appURL != nil {
                Button("Start engine") { Engine.start(); DispatchQueue.main.asyncAfter(deadline: .now() + 6, execute: retry) }
            }
            #endif
            Button("Retry", action: retry).bold()
        }
        .padding(12)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        .padding(.horizontal, 16)
        .frame(maxWidth: 760)
    }
}

struct EmptyState: View {
    @Environment(ChatStore.self) private var store
    private let suggestions: [(String, String, String)] = [
        ("Write a reply", "to a customer asking about a late order", "envelope"),
        ("Plan my week", "from this list of tasks", "calendar"),
        ("Find the bug", "in a piece of code I paste", "ladybug"),
        ("Three captions", "for a photo of a new product", "camera"),
    ]
    private var greeting: String {
        let h = Calendar.current.component(.hour, from: .now)
        return h < 5 ? "Up late?" : h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening"
    }

    var body: some View {
        VStack(spacing: 14) {
            Logo(size: 76).shadow(color: .primary.opacity(0.15), radius: 18)
            Text(greeting).font(.largeTitle.weight(.bold))
            Text("Private AI that runs on your own Mac.\nYour chats stay on your devices.")
                .multilineTextAlignment(.center).foregroundStyle(.secondary)
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 230), spacing: 10)], spacing: 10) {
                ForEach(suggestions, id: \.0) { s in
                    Button {
                        store.draft = s.0 + " " + s.1 + ": "
                        store.focusTick += 1
                    } label: {
                        HStack(alignment: .top, spacing: 10) {
                            Image(systemName: s.2).frame(width: 20).foregroundStyle(.secondary)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(s.0).fontWeight(.semibold)
                                Text(s.1).font(.callout).foregroundStyle(.secondary)
                            }
                            Spacer(minLength: 0)
                        }
                        .padding(14)
                        .background(Theme.field, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).strokeBorder(.quaternary))
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                }
            }
            .frame(maxWidth: 600)
            .padding(.top, 14)
        }
        .padding(24)
    }
}

struct MessageRow: View {
    @Environment(ChatStore.self) private var store
    let message: ChatMessage
    let isLast: Bool
    @State private var copied = false

    var body: some View {
        if message.isUser {
            HStack {
                Spacer(minLength: 60)
                Text(message.content)
                    .textSelection(.enabled)
                    .padding(.horizontal, 15).padding(.vertical, 10)
                    .foregroundStyle(userInk)
                    .background(Theme.userBubble, in: UnevenRoundedRectangle(topLeadingRadius: 20, bottomLeadingRadius: 20,
                                                                            bottomTrailingRadius: 6, topTrailingRadius: 20,
                                                                            style: .continuous))
            }
        } else {
            VStack(alignment: .leading, spacing: 8) {
                if let err = message.error {
                    Label(err, systemImage: "exclamationmark.triangle").foregroundStyle(.red)
                } else if message.content.isEmpty && message.streaming {
                    HStack(spacing: 10) {
                        PulseOrb()
                        Text(message.status ?? "Thinking…").foregroundStyle(.secondary)
                    }
                } else {
                    MarkdownView(text: message.content, streaming: message.streaming)
                }
                if !message.streaming { actions }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    @Environment(\.colorScheme) private var scheme
    private var userInk: Color { scheme == .dark ? .black : .white }

    private var actions: some View {
        HStack(spacing: 4) {
            if !message.content.isEmpty {
                iconButton(copied ? "checkmark" : "doc.on.doc", "Copy") {
                    Clipboard.copy(message.content); copied = true
                    DispatchQueue.main.asyncAfter(deadline: .now() + 1.4) { copied = false }
                }
                iconButton("speaker.wave.2", "Read aloud") { store.speak(message.content) }
                ShareLink(item: message.content) { Image(systemName: "square.and.arrow.up").frame(width: 28, height: 26) }
                    .buttonStyle(.borderless).help("Share")
            }
            if isLast {
                iconButton("arrow.clockwise", "Try again") { store.retry() }
                iconButton("pencil", "Edit my question") { store.editLast() }
            }
            if let m = message.meta { MetaChips(meta: m).padding(.leading, 4) }
        }
        .foregroundStyle(.secondary)
        .font(.callout)
    }

    private func iconButton(_ icon: String, _ help: String, _ action: @escaping () -> Void) -> some View {
        Button(action: action) { Image(systemName: icon).frame(width: 28, height: 26).contentShape(Rectangle()) }
            .buttonStyle(.borderless).help(help).accessibilityLabel(help)
    }
}

struct MetaChips: View {
    let meta: MessageMeta
    var body: some View {
        HStack(spacing: 6) {
            if let s = meta.skill { chip("✦ " + s) }
            if let t = meta.tools, !t.isEmpty { chip("⚙ " + t.joined(separator: ", ")) }
            if let f = meta.first_token_secs { Text("\(f, specifier: "%.1f")s").font(.caption).help("Time to first word") }
            if meta.stopped == true { Text("stopped").font(.caption) }
        }
    }
    private func chip(_ s: String) -> some View {
        Text(s).font(.caption).lineLimit(1).padding(.horizontal, 8).padding(.vertical, 2)
            .background(.quaternary.opacity(0.6), in: Capsule())
    }
}

struct PulseOrb: View {
    @State private var on = false
    var body: some View {
        Circle().fill(.primary).frame(width: 12, height: 12)
            .scaleEffect(on ? 1 : 0.6).opacity(on ? 1 : 0.35)
            .animation(.easeInOut(duration: 0.7).repeatForever(autoreverses: true), value: on)
            .onAppear { on = true }
    }
}

struct Composer: View {
    @Environment(ChatStore.self) private var store
    @FocusState private var focused: Bool

    var body: some View {
        @Bindable var store = store
        VStack(spacing: 6) {
            HStack(alignment: .bottom, spacing: 8) {
                TextField("Message Source Linga", text: $store.draft, axis: .vertical)
                    .textFieldStyle(.plain)
                    .lineLimit(1...10)
                    .focused($focused)
                    .padding(.vertical, 10)
                    .padding(.leading, 16)
                    .onSubmit { store.send() }
                    .onChange(of: store.draft) { store.draftChanged() }
                    #if os(iOS)
                    .submitLabel(.return)
                    #endif
                Button {
                    if store.isStreaming { store.stop() } else { store.send() }
                } label: {
                    Image(systemName: store.isStreaming ? "stop.fill" : "arrow.up")
                        .font(.system(size: 15, weight: .bold))
                        .frame(width: 34, height: 34)
                        .foregroundStyle(scheme == .dark ? .black : .white)
                        .background(Circle().fill(.primary))
                }
                .buttonStyle(.plain)
                .disabled(!store.isStreaming && store.draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                .opacity(!store.isStreaming && store.draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? 0.3 : 1)
                .keyboardShortcut(store.isStreaming ? "." : .return, modifiers: .command)
                .padding(5)
                .sensoryFeedback(.impact(weight: .light), trigger: store.isStreaming)
            }
            .background(Theme.field, in: RoundedRectangle(cornerRadius: 24, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 24, style: .continuous).strokeBorder(.quaternary))
            .shadow(color: .black.opacity(0.08), radius: 14, y: 4)
            #if os(macOS)
            Text("Runs privately on your Mac · Return to send · ⌥Space from any app")
                .font(.caption2).foregroundStyle(.tertiary)
            #endif
        }
        .frame(maxWidth: 760)
        .padding(.horizontal, 14).padding(.top, 6).padding(.bottom, 10)
        .frame(maxWidth: .infinity)
        .background(.bar.opacity(0.0))
        .onChange(of: store.focusTick) { focused = true }
        .onAppear { focused = true }
        #if os(macOS)
        .onReceive(NotificationCenter.default.publisher(for: .slFocusComposer)) { _ in focused = true }
        #endif
    }

    @Environment(\.colorScheme) private var scheme
}
