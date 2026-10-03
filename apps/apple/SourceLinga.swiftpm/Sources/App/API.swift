import Foundation
import Network
import Security

// MARK: - What the server sends

struct ServerInfo: Decodable { var name: String; var version: String?; var paired: Bool; var computer: String? }
struct ServerStatus: Decodable { var ollama: Bool; var model: String }

struct MessageMeta: Codable, Equatable {
    var skill: String?
    var tools: [String]?
    var first_token_secs: Double?
    var tps: Double?
    var stopped: Bool?
}

struct StoredMessage: Codable { var role: String; var content: String; var meta: MessageMeta? }
struct ConvoSummary: Codable, Identifiable, Hashable {
    var id: String; var title: String; var updated: Double; var count: Int?; var preview: String?
}
struct StoredConvo: Codable { var id: String; var title: String; var updated: Double; var messages: [StoredMessage] }

enum StreamEvent {
    case status(String)
    case token(String)
    case tool(String)
    case done(content: String, meta: MessageMeta, error: String?)
}

enum APIError: LocalizedError {
    case notPaired, unreachable, http(Int, String)
    var errorDescription: String? {
        switch self {
        case .notPaired: return "This device isn't paired with your Mac yet."
        case .unreachable: return "Can't reach your Mac. Check that it's awake and on the same Wi-Fi."
        case .http(let code, let msg): return msg.isEmpty ? "The Mac answered with error \(code)." : msg
        }
    }
}

// MARK: - Where the AI lives

/// The Mac running Source Linga. On that Mac itself it is 127.0.0.1 and needs no key;
/// everywhere else it is a Wi-Fi address plus the key the Mac gave this device when it was paired.
struct Endpoint: Codable, Equatable {
    var base: URL
    var name: String
    var key: String?
    static let local = Endpoint(base: URL(string: "http://127.0.0.1:8777")!, name: "This Mac", key: nil)
    var isLocal: Bool { base.host == "127.0.0.1" || base.host == "localhost" }

    static func load() -> Endpoint? {
        guard let data = UserDefaults.standard.data(forKey: "endpoint"),
              var ep = try? JSONDecoder().decode(Endpoint.self, from: data) else { return nil }
        ep.key = Keychain.get("device-key")
        return ep
    }

    func save() {
        var copy = self
        copy.key = nil  // the key lives in the Keychain, not in preferences
        UserDefaults.standard.set(try? JSONEncoder().encode(copy), forKey: "endpoint")
        if let key { Keychain.set("device-key", key) } else { Keychain.delete("device-key") }
    }

    static func forget() {
        UserDefaults.standard.removeObject(forKey: "endpoint")
        Keychain.delete("device-key")
    }

    /// Accepts "192.168.0.10", "my-mac.local", "http://host:8777/app" and the like.
    static func parse(_ text: String) -> URL? {
        var t = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if t.isEmpty { return nil }
        if !t.contains("://") { t = "http://" + t }
        guard var c = URLComponents(string: t), c.host?.isEmpty == false else { return nil }
        if c.port == nil { c.port = 8777 }
        c.path = ""; c.query = nil; c.fragment = nil
        return c.url
    }
}

enum Keychain {
    private static let service = "com.sourcelinga.app"
    static func set(_ account: String, _ value: String) {
        delete(account)
        let q: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service,
                                kSecAttrAccount as String: account, kSecValueData as String: Data(value.utf8),
                                kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlock]
        SecItemAdd(q as CFDictionary, nil)
    }
    static func get(_ account: String) -> String? {
        let q: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service,
                                kSecAttrAccount as String: account, kSecReturnData as String: true]
        var out: AnyObject?
        guard SecItemCopyMatching(q as CFDictionary, &out) == errSecSuccess, let d = out as? Data else { return nil }
        return String(data: d, encoding: .utf8)
    }
    static func delete(_ account: String) {
        let q: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service,
                                kSecAttrAccount as String: account]
        SecItemDelete(q as CFDictionary)
    }
}

// MARK: - Talking to the Mac

final class API: @unchecked Sendable {
    let ep: Endpoint
    private let session: URLSession
    private let streamSession: URLSession

    init(_ ep: Endpoint) {
        self.ep = ep
        let c = URLSessionConfiguration.ephemeral
        c.timeoutIntervalForRequest = 20
        c.waitsForConnectivity = false
        session = URLSession(configuration: c)
        let s = URLSessionConfiguration.ephemeral
        s.timeoutIntervalForRequest = 600  // a long answer can pause while a tool runs
        streamSession = URLSession(configuration: s)
    }

    private func request(_ path: String, body: Any? = nil) -> URLRequest {
        var r = URLRequest(url: URL(string: path, relativeTo: ep.base)!)
        if let key = ep.key { r.setValue("Bearer " + key, forHTTPHeaderField: "Authorization") }
        if let body {
            r.httpMethod = "POST"
            r.setValue("application/json", forHTTPHeaderField: "Content-Type")
            r.httpBody = try? JSONSerialization.data(withJSONObject: body)
        }
        return r
    }

    private func check(_ data: Data, _ resp: URLResponse) throws -> Data {
        let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
        if code == 401 { throw APIError.notPaired }
        if !(200..<300).contains(code) {
            let msg = (try? JSONSerialization.jsonObject(with: data) as? [String: Any])?["error"] as? String
            throw APIError.http(code, msg ?? "")
        }
        return data
    }

    private func send(_ r: URLRequest) async throws -> Data {
        do {
            let (data, resp) = try await session.data(for: r)
            return try check(data, resp)
        } catch let e as URLError where e.code != .cancelled {
            throw APIError.unreachable
        }
    }

    func get<T: Decodable>(_ path: String, as: T.Type = T.self) async throws -> T {
        try JSONDecoder().decode(T.self, from: try await send(request(path)))
    }

    @discardableResult
    func post(_ path: String, _ body: [String: Any]) async throws -> Data {
        try await send(request(path, body: body))
    }

    func info() async throws -> ServerInfo { try await get("/api/info") }
    func status() async throws -> ServerStatus { try await get("/api/status") }
    func convos() async throws -> [ConvoSummary] { try await get("/api/convos") }
    func convo(_ id: String) async throws -> StoredConvo { try await get("/api/convos/" + id) }
    func delete(_ id: String) async throws { try await post("/api/convos/\(id)/delete", [:]) }

    func save(_ id: String, title: String, messages: [StoredMessage]) async throws -> ConvoSummary {
        let msgs: [[String: Any]] = messages.map { m in
            var d: [String: Any] = ["role": m.role, "content": m.content]
            if let meta = m.meta, let data = try? JSONEncoder().encode(meta),
               let obj = try? JSONSerialization.jsonObject(with: data) { d["meta"] = obj }
            return d
        }
        return try JSONDecoder().decode(ConvoSummary.self,
                                        from: try await post("/api/convos/" + id, ["title": title, "messages": msgs]))
    }

    func warm() { Task { _ = try? await send(request("/api/warm")) } }

    func readAhead(_ messages: [[String: String]]) {
        Task { _ = try? await post("/api/read_ahead", ["messages": messages]) }
    }

    /// Pairs this device with the 6-digit code shown on the Mac; returns the device key.
    static func pair(base: URL, code: String) async throws -> (key: String, computer: String) {
        var r = URLRequest(url: base.appendingPathComponent("pair"))
        r.httpMethod = "POST"
        r.timeoutInterval = 15
        r.setValue("application/json", forHTTPHeaderField: "Content-Type")
        r.httpBody = try JSONSerialization.data(withJSONObject: ["code": code, "app": true])
        let data: Data, resp: URLResponse
        do { (data, resp) = try await URLSession(configuration: .ephemeral).data(for: r) } catch { throw APIError.unreachable }
        let obj = (try? JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
        let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
        guard code == 200, let key = obj["key"] as? String else {
            throw APIError.http(code, (obj["error"] as? String).map { $0.prefix(1).uppercased() + $0.dropFirst() } ?? "")
        }
        return (key, obj["computer"] as? String ?? base.host ?? "Mac")
    }

    /// The answer, streamed word by word (server-sent events from /api/chat/stream).
    /// Cancelling the task closes the connection, which stops the model on the Mac.
    func stream(_ messages: [[String: String]]) -> AsyncThrowingStream<StreamEvent, Error> {
        let req = request("/api/chat/stream", body: ["messages": messages])
        let session = streamSession
        return AsyncThrowingStream { cont in
            let task = Task {
                do {
                    let (bytes, resp) = try await session.bytes(for: req)
                    let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
                    if code == 401 { throw APIError.notPaired }
                    if code != 200 { throw APIError.http(code, "") }
                    for try await line in bytes.lines {
                        guard line.hasPrefix("data: "),
                              let ev = try? JSONSerialization.jsonObject(with: Data(line.dropFirst(6).utf8)) as? [String: Any]
                        else { continue }
                        switch ev["type"] as? String {
                        case "token": cont.yield(.token(ev["text"] as? String ?? ""))
                        case "status": cont.yield(.status(ev["text"] as? String ?? ""))
                        case "tool": cont.yield(.tool(ev["name"] as? String ?? "a tool"))
                        case "done":
                            let meta = MessageMeta(skill: ev["skill"] as? String, tools: ev["tools"] as? [String],
                                                   first_token_secs: ev["first_token_secs"] as? Double,
                                                   tps: ev["tps"] as? Double)
                            cont.yield(.done(content: ev["content"] as? String ?? "", meta: meta, error: ev["error"] as? String))
                        default: break
                        }
                    }
                    cont.finish()
                } catch let e as URLError where e.code != .cancelled {
                    cont.finish(throwing: APIError.unreachable)
                } catch {
                    cont.finish(throwing: error)
                }
            }
            cont.onTermination = { _ in task.cancel() }
        }
    }
}

// MARK: - Finding Macs on the Wi-Fi (Bonjour)

struct FoundMac: Identifiable, Hashable { var id: String { name }; var name: String; var endpoint: NWEndpoint }

@Observable
final class Discovery {
    var found: [FoundMac] = []
    private var browser: NWBrowser?

    func start() {
        guard browser == nil else { return }
        let b = NWBrowser(for: .bonjour(type: "_sourcelinga._tcp", domain: nil), using: .tcp)
        b.browseResultsChangedHandler = { [weak self] results, _ in
            self?.found = results.compactMap { r in
                if case let .service(name, _, _, _) = r.endpoint { return FoundMac(name: name, endpoint: r.endpoint) }
                return nil
            }.sorted { $0.name < $1.name }
        }
        b.start(queue: .main)
        browser = b
    }

    func stop() { browser?.cancel(); browser = nil }

    /// Turns a Bonjour service into an http address (IPv4, so it also works in a plain URL).
    static func resolve(_ service: NWEndpoint) async -> URL? {
        await withCheckedContinuation { (cont: CheckedContinuation<URL?, Never>) in
            let params = NWParameters.tcp
            if let ip = params.defaultProtocolStack.internetProtocol as? NWProtocolIP.Options { ip.version = .v4 }
            let once = Once(NWConnection(to: service, using: params), cont)
            once.conn.stateUpdateHandler = { state in
                switch state {
                case .ready:
                    if case let .hostPort(host, port)? = once.conn.currentPath?.remoteEndpoint {
                        var h = "\(host)"
                        if let pct = h.firstIndex(of: "%") { h = String(h[..<pct]) }
                        once.finish(URL(string: "http://\(h):\(port.rawValue)"))
                    } else { once.finish(nil) }
                case .failed, .cancelled: once.finish(nil)
                default: break
                }
            }
            once.conn.start(queue: .main)
            DispatchQueue.main.asyncAfter(deadline: .now() + 6) { once.finish(nil) }
        }
    }

    /// Resumes the continuation exactly once (every callback runs on the main queue).
    private final class Once: @unchecked Sendable {
        let conn: NWConnection
        private var cont: CheckedContinuation<URL?, Never>?
        init(_ conn: NWConnection, _ cont: CheckedContinuation<URL?, Never>) { self.conn = conn; self.cont = cont }
        func finish(_ url: URL?) {
            guard let c = cont else { return }
            cont = nil
            conn.cancel()
            c.resume(returning: url)
        }
    }
}
