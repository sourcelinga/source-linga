import Foundation
import SwiftUI
import AVFoundation

struct ChatMessage: Identifiable, Equatable {
    let id = UUID()
    var role: String
    var content: String
    var meta: MessageMeta? = nil
    var status: String? = nil
    var error: String? = nil
    var streaming = false
    var isUser: Bool { role == "user" }
}

struct Conversation {
    var id: String = Conversation.newID()
    var title: String = ""
    var messages: [ChatMessage] = []
    static func newID() -> String {
        String(Int(Date().timeIntervalSince1970 * 1000), radix: 36) + "-" + UUID().uuidString.prefix(12).lowercased()
    }
}

enum Connection: Equatable { case connecting, online(model: String), engineStarting, offline(String), unpaired }

/// Everything the chat screens show: the list of chats (shared with every device through the Mac),
/// the open chat, and the answer that is streaming in.
@MainActor @Observable
final class ChatStore {
    var endpoint: Endpoint?
    var connection: Connection = .connecting
    var computer: String = ""
    var convos: [ConvoSummary] = []
    var current = Conversation()
    var selection: String?
    var isStreaming = false
    var draft = ""
    var focusTick = 0  // bump to put the cursor in the composer

    private var api: API?
    private var streamTask: Task<Void, Never>?
    private var aheadTask: Task<Void, Never>?
    private var lastAhead = ""
    private let speech = AVSpeechSynthesizer()

    init() {
        #if os(macOS)
        endpoint = Endpoint.load() ?? .local
        #else
        endpoint = Endpoint.load()
        #endif
        if let endpoint { api = API(endpoint) } else { connection = .unpaired }
    }

    // MARK: connection

    func connect(_ ep: Endpoint) {
        endpoint = ep
        ep.save()
        api = API(ep)
        convos = []
        newChat()
        Task { await refresh() }
    }

    func disconnect() {
        Endpoint.forget()
        #if os(macOS)
        connect(.local)
        #else
        endpoint = nil; api = nil; convos = []; connection = .unpaired; newChat()
        #endif
    }

    func refresh() async {
        guard let api else { connection = .unpaired; return }
        do {
            let info = try await api.info()
            computer = info.computer ?? ""
            guard info.paired else { connection = .unpaired; return }
            let st = try await api.status()
            connection = st.ollama ? .online(model: st.model) : .engineStarting
            convos = try await api.convos()
            api.warm()
        } catch APIError.notPaired {
            connection = .unpaired
        } catch {
            connection = .offline(error.localizedDescription)
        }
    }

    var isOnline: Bool { if case .online = connection { return true }; return false }

    var statusLine: String {
        switch connection {
        case .connecting: return "Connecting…"
        case .online(let m): return endpoint?.isLocal == true ? m : "\(computer.isEmpty ? "Mac" : computer) · \(m)"
        case .engineStarting: return "AI engine is starting…"
        case .offline: return "Offline"
        case .unpaired: return "Not paired"
        }
    }

    // MARK: chats

    func newChat() {
        stop()
        current = Conversation()
        selection = nil
        focusTick += 1
    }

    func open(_ id: String) {
        guard id != current.id, let api else { return }
        stop()
        selection = id
        Task {
            do {
                let c = try await api.convo(id)
                current = Conversation(id: c.id, title: c.title, messages: c.messages.map {
                    ChatMessage(role: $0.role, content: $0.content, meta: $0.meta)
                })
            } catch { connection = .offline(error.localizedDescription) }
        }
    }

    func delete(_ id: String) {
        convos.removeAll { $0.id == id }
        if current.id == id { newChat() }
        Task { try? await api?.delete(id) }
    }

    // MARK: asking

    func send(_ text: String? = nil) {
        let t = (text ?? draft).trimmingCharacters(in: .whitespacesAndNewlines)
        guard !t.isEmpty, !isStreaming else { return }
        current.messages.append(ChatMessage(role: "user", content: t))
        if text == nil { draft = "" }
        ask()
    }

    func retry() {
        guard !isStreaming, let last = current.messages.last, !last.isUser else { return }
        current.messages.removeLast()
        ask()
    }

    /// Takes the last question back into the composer so it can be changed and sent again.
    func editLast() {
        guard !isStreaming, let i = current.messages.lastIndex(where: { $0.isUser }) else { return }
        draft = current.messages[i].content
        current.messages.removeSubrange(i...)
        focusTick += 1
    }

    func stop() { streamTask?.cancel(); streamTask = nil }

    private func ask() {
        guard let api else { return }
        let history = current.messages.filter { $0.error == nil }.map { ["role": $0.role, "content": $0.content] }
        current.messages.append(ChatMessage(role: "assistant", content: "", status: "Reading your notes…", streaming: true))
        let idx = current.messages.count - 1
        let convoID = current.id
        isStreaming = true
        streamTask = Task { [weak self] in
            var stopped = false
            do {
                for try await ev in api.stream(history) {
                    guard let self, self.current.id == convoID, idx < self.current.messages.count else { break }
                    switch ev {
                    case .token(let t):
                        self.current.messages[idx].content += t
                        self.current.messages[idx].status = nil
                    case .status(let s): self.current.messages[idx].status = s
                    case .tool(let name):
                        self.current.messages[idx].status = "Using \(name.replacingOccurrences(of: "_", with: " "))…"
                        self.current.messages[idx].content = ""
                    case .done(let content, let meta, let error):
                        if !content.isEmpty { self.current.messages[idx].content = content }
                        self.current.messages[idx].meta = meta
                        if let error, self.current.messages[idx].content.isEmpty { self.current.messages[idx].error = error }
                    }
                }
                if Task.isCancelled { stopped = true }
            } catch is CancellationError {
                stopped = true
            } catch {
                if let self, self.current.id == convoID, idx < self.current.messages.count {
                    self.current.messages[idx].error = error.localizedDescription
                    if case APIError.unreachable = error { self.connection = .offline(error.localizedDescription) }
                    if case APIError.notPaired = error { self.connection = .unpaired }
                }
            }
            guard let self else { return }
            if self.current.id == convoID, idx < self.current.messages.count {
                var m = self.current.messages[idx]
                m.streaming = false
                m.status = nil
                if stopped { m.meta = (m.meta ?? MessageMeta()); m.meta?.stopped = true }
                if m.content.isEmpty && m.error == nil && !stopped { m.error = "No answer came back." }
                self.current.messages[idx] = m
                if case .offline = self.connection, m.error == nil { self.connection = .connecting; Task { await self.refresh() } }
                await self.save()
            }
            self.isStreaming = false
            self.streamTask = nil
        }
    }

    private func save() async {
        guard let api, current.messages.contains(where: { !$0.isUser && !$0.content.isEmpty }) else { return }
        let msgs = current.messages.filter { $0.error == nil }.map { StoredMessage(role: $0.role, content: $0.content, meta: $0.meta) }
        if let s = try? await api.save(current.id, title: current.title, messages: msgs) {
            current.title = s.title
            selection = s.id
            convos.removeAll { $0.id == s.id }
            convos.insert(s, at: 0)
        }
    }

    /// After a short pause in typing, the Mac starts reading the draft, so Send answers sooner.
    func draftChanged() {
        aheadTask?.cancel()
        let t = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard t.count >= 8, !isStreaming, t != lastAhead, let api else { return }
        let history = current.messages.filter { $0.error == nil }.map { ["role": $0.role, "content": $0.content] }
        aheadTask = Task { [weak self] in
            try? await Task.sleep(for: .milliseconds(1500))
            guard !Task.isCancelled, let self, !self.isStreaming else { return }
            self.lastAhead = t
            api.readAhead(history + [["role": "user", "content": t]])
        }
    }

    // MARK: extras

    func speak(_ text: String) {
        if speech.isSpeaking { speech.stopSpeaking(at: .immediate); return }
        let plain = text.replacingOccurrences(of: "```[\\s\\S]*?```", with: " (code) ", options: .regularExpression)
            .replacingOccurrences(of: "[*#`>|_]", with: "", options: .regularExpression)
        speech.speak(AVSpeechUtterance(string: plain))
    }

    var toolsURL: URL? { endpoint?.base }
}
