#if os(macOS)
import SwiftUI
import AppKit

// MARK: - One-click setup on the Mac (no Terminal)
//
// The Mac app carries the whole engine in Contents/Resources/engine. "Set up" copies it to
// ~/Library/Application Support/SourceLinga/engine and runs its install.sh there, showing progress as
// friendly steps: Apple's developer tools (for Python), Ollama, the AI model, the background service.

enum Setup {
    static let home = FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent("Library/Application Support/SourceLinga")
    static var engineDir: URL { home.appendingPathComponent("engine") }
    static var bundledEngine: URL? {
        guard let u = Bundle.main.resourceURL?.appendingPathComponent("engine"),
              FileManager.default.fileExists(atPath: u.appendingPathComponent("install.sh").path) else { return nil }
        return u
    }

    // What this Mac has
    static var memoryGB: Int { Int(ProcessInfo.processInfo.physicalMemory / 1_073_741_824) }
    static var isAppleSilicon: Bool {
        var v: Int32 = 0; var n = MemoryLayout<Int32>.size
        return sysctlbyname("hw.optional.arm64", &v, &n, nil, 0) == 0 && v == 1
    }
    static var freeDiskGB: Int {
        let v = try? FileManager.default.homeDirectoryForCurrentUser
            .resourceValues(forKeys: [.volumeAvailableCapacityForImportantUsageKey])
        return Int((v?.volumeAvailableCapacityForImportantUsage ?? 0) / 1_000_000_000)
    }
    static var modelName: String { memoryGB < 14 ? "qwen3.5:4b" : "qwen3.5:9b" }
    static var downloadGB: Double { memoryGB < 14 ? 3.7 : 7.0 }

    /// Apple's free Command Line Tools provide the Python the engine runs on.
    static var hasDevTools: Bool {
        let r = run("/usr/bin/xcode-select", ["-p"])
        return r.status == 0 && FileManager.default.fileExists(atPath: r.out.trimmingCharacters(in: .whitespacesAndNewlines))
    }

    static func requestDevTools() { _ = run("/usr/bin/xcode-select", ["--install"]) }

    @discardableResult
    static func run(_ tool: String, _ args: [String], cwd: URL? = nil) -> (status: Int32, out: String) {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: tool)
        p.arguments = args
        if let cwd { p.currentDirectoryURL = cwd }
        let pipe = Pipe()
        p.standardOutput = pipe; p.standardError = pipe
        do { try p.run() } catch { return (-1, error.localizedDescription) }
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        p.waitUntilExit()
        return (p.terminationStatus, String(decoding: data, as: UTF8.self))
    }

    static func uninstall() {
        let script = engineDir.appendingPathComponent("uninstall.sh")
        if FileManager.default.fileExists(atPath: script.path) { run("/bin/bash", [script.path], cwd: engineDir) }
        else if let b = bundledEngine { run("/bin/bash", [b.appendingPathComponent("uninstall.sh").path]) }
    }
}

@MainActor @Observable
final class SetupModel {
    enum Step: Int, CaseIterable { case tools, ollama, model, service, done
        var title: String {
            switch self {
            case .tools: return "Apple developer tools"
            case .ollama: return "Ollama, the AI runtime"
            case .model: return "The AI model"
            case .service: return "Background service"
            case .done: return "Ready"
            }
        }
        var icon: String {
            switch self {
            case .tools: return "hammer"
            case .ollama: return "cpu"
            case .model: return "arrow.down.circle"
            case .service: return "bolt.horizontal.circle"
            case .done: return "checkmark.seal"
            }
        }
    }
    enum Phase: Equatable { case idle, waitingForTools, running, finished, failed(String) }

    var phase: Phase = .idle
    var step: Step = .tools
    var detail = ""
    var progress: Double? = nil
    var log: [String] = []
    private var process: Process?

    func start() {
        guard phase != .running else { return }
        log = []
        if !Setup.hasDevTools {
            phase = .waitingForTools; step = .tools
            detail = "macOS is asking to install its free developer tools. Click Install in that window and agree. This takes 5–15 minutes."
            Setup.requestDevTools()
            Task { await waitForTools() }
            return
        }
        install()
    }

    private func waitForTools() async {
        while phase == .waitingForTools {
            try? await Task.sleep(for: .seconds(4))
            if Setup.hasDevTools { install(); return }
        }
    }

    private func install() {
        phase = .running; step = .ollama; progress = nil
        detail = "Preparing…"
        Task.detached { [weak self] in
            do { try Self.copyEngine() } catch {
                await MainActor.run { self?.phase = .failed("Couldn't copy the engine: \(error.localizedDescription)") }
                return
            }
            await self?.runInstaller()
        }
    }

    /// Copies the bundled engine over the installed one. Your own files (settings, house rules, chats, notes)
    /// aren't in the bundle, so updates never touch them.
    nonisolated private static func copyEngine() throws {
        guard let src = Setup.bundledEngine else { throw CocoaError(.fileNoSuchFile) }
        try FileManager.default.createDirectory(at: Setup.engineDir, withIntermediateDirectories: true)
        let r = Setup.run("/usr/bin/rsync", ["-a", src.path + "/", Setup.engineDir.path + "/"])
        if r.status != 0 { throw NSError(domain: "rsync", code: Int(r.status), userInfo: [NSLocalizedDescriptionKey: r.out]) }
        // Phones and other Macs download this Mac app from the engine's /get page.
        let dist = Setup.engineDir.appendingPathComponent("dist")
        try? FileManager.default.createDirectory(at: dist, withIntermediateDirectories: true)
        Setup.run("/usr/bin/ditto", ["-c", "-k", "--keepParent", Bundle.main.bundlePath,
                                     dist.appendingPathComponent("SourceLinga-mac.zip").path])
    }

    nonisolated private func runInstaller() async {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/bin/bash")
        p.arguments = ["install.sh"]
        p.currentDirectoryURL = Setup.engineDir
        var env = ProcessInfo.processInfo.environment
        env["PATH"] = "/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin"
        env["SL_FROM_APP"] = "1"
        env["PYTHONUNBUFFERED"] = "1"
        p.environment = env
        let pipe = Pipe()
        p.standardOutput = pipe; p.standardError = pipe
        var pending = ""
        pipe.fileHandleForReading.readabilityHandler = { [weak self] h in
            let chunk = String(decoding: h.availableData, as: UTF8.self)
            if chunk.isEmpty { return }
            pending += chunk
            var lines = pending.components(separatedBy: CharacterSet(charactersIn: "\r\n"))
            pending = lines.removeLast()
            let ready = lines.filter { !$0.trimmingCharacters(in: .whitespaces).isEmpty }
            if !ready.isEmpty { Task { @MainActor in ready.forEach { self?.handle($0) } } }
        }
        p.terminationHandler = { [weak self] proc in
            pipe.fileHandleForReading.readabilityHandler = nil
            let ok = proc.terminationStatus == 0
            Task { @MainActor in
                guard let self else { return }
                if ok { self.step = .done; self.progress = 1; self.phase = .finished; self.detail = "Source Linga is ready." }
                else {
                    let why = self.log.last(where: { $0.hasPrefix("✗") }) ?? "Setup stopped (code \(proc.terminationStatus))."
                    self.phase = .failed(why)
                }
            }
        }
        do { try p.run() } catch {
            await MainActor.run { self.phase = .failed(error.localizedDescription) }
            return
        }
        await MainActor.run { self.process = p }
    }

    private func handle(_ line: String) {
        log.append(line)
        if log.count > 400 { log.removeFirst(log.count - 400) }
        if line.contains("Downloading Ollama") { step = .ollama; detail = "Downloading Ollama (about 200 MB)…"; progress = nil }
        else if line.contains("Starting Ollama") { step = .ollama; detail = "Starting Ollama…" }
        else if line.hasPrefix("→ Pulling") {
            step = .model; progress = 0
            let m = line.replacingOccurrences(of: "→ Pulling ", with: "")
            detail = m.contains("embed") ? "Downloading the search model (0.3 GB)…" : "Downloading \(m) (about \(String(format: "%.1f", Setup.downloadGB)) GB). You can keep using your Mac."
        } else if line.hasPrefix("pull "), let pct = line.range(of: #"(\d+)%"#, options: .regularExpression) {
            progress = (Double(line[pct].dropLast()) ?? 0) / 100
        } else if line.contains("Service installed") { step = .service; progress = nil; detail = "Starting the background service…" }
        else if line.contains("First index") { detail = "Almost done…" }
        else if line.hasPrefix("→ This Mac has") { detail = String(line.dropFirst(2)) }
    }

    func cancel() {
        process?.terminate()
        phase = .idle
    }
}

// MARK: - Screens

/// First launch on a Mac without the engine: set it up here, or use the AI on another Mac.
struct WelcomeView: View {
    @Environment(ChatStore.self) private var store
    @State private var model = SetupModel()
    @State private var showConnect = false

    var body: some View {
        ScrollView {
            VStack(spacing: 22) {
                Logo(size: 88).padding(12).glass(RoundedRectangle(cornerRadius: 34, style: .continuous)).padding(.top, 36)
                VStack(spacing: 8) {
                    Text(model.phase == .idle ? "Welcome to Source Linga" : "Setting up Source Linga")
                        .font(.largeTitle.bold())
                    Text("A private AI that runs on your own Mac. Nothing you type leaves it. No account, no sign-in, no Terminal.")
                        .multilineTextAlignment(.center).foregroundStyle(.secondary).frame(maxWidth: 440)
                }
                switch model.phase {
                case .idle: intro
                default: SetupProgressView(model: model) {
                    Task { await store.refresh() }
                }
                }
            }
            .frame(maxWidth: 520)
            .padding(28)
            .frame(maxWidth: .infinity)
        }
        .background(LiquidBackdrop())
        .sheet(isPresented: $showConnect) {
            ConnectView().frame(width: 480, height: 600)
                .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Cancel") { showConnect = false } } }
        }
        .onChange(of: store.endpoint) { showConnect = false }
    }

    private var intro: some View {
        VStack(spacing: 16) {
            VStack(alignment: .leading, spacing: 12) {
                fact("memorychip", "This Mac", "\(Setup.memoryGB) GB memory · \(Setup.isAppleSilicon ? "Apple silicon" : "Intel (answers will be slow)")")
                fact("arrow.down.circle", "One-time download", "about \(Int(Setup.downloadGB.rounded()) + 1) GB (model \(Setup.modelName)), 10–30 minutes")
                fact("internaldrive", "Free space", Setup.freeDiskGB >= 12 ? "\(Setup.freeDiskGB) GB free: enough" : "\(Setup.freeDiskGB) GB free: please free up at least 12 GB first")
                fact("lock.shield", "Private", "After setup it works offline. Your chats stay on your devices.")
            }
            .padding(18)
            .glassCard(22)

            VStack(spacing: 12) {
                Button { model.start() } label: { Label("Set up on this Mac", systemImage: "sparkles") }
                    .buttonStyle(GlassPrimaryButtonStyle())
                    .disabled(Setup.bundledEngine == nil || Setup.freeDiskGB < 8)
                Button { showConnect = true } label: { Label("Use the AI on another Mac", systemImage: "laptopcomputer.and.iphone") }
                    .buttonStyle(GlassSecondaryButtonStyle())
            }
            if Setup.bundledEngine == nil {
                Text("This copy of the app doesn't include the engine. Download the full app from the Releases page.")
                    .font(.callout).foregroundStyle(.secondary)
            }
        }
    }

    private func fact(_ icon: String, _ title: String, _ value: String) -> some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: icon).font(.title3).foregroundStyle(Theme.accentGradient).frame(width: 26)
            VStack(alignment: .leading, spacing: 2) {
                Text(title).fontWeight(.semibold)
                Text(value).font(.callout).foregroundStyle(.secondary)
            }
            Spacer(minLength: 0)
        }
    }
}

struct SetupProgressView: View {
    let model: SetupModel
    let onDone: () -> Void
    @State private var showLog = false

    var body: some View {
        VStack(spacing: 16) {
            VStack(alignment: .leading, spacing: 14) {
                ForEach(SetupModel.Step.allCases, id: \.self) { s in row(s) }
            }
            .padding(18)
            .glassCard(22)

            VStack(spacing: 10) {
                if let p = model.progress, model.phase == .running {
                    ProgressView(value: p).tint(Theme.accent)
                }
                Text(model.detail).font(.callout).foregroundStyle(.secondary).multilineTextAlignment(.center)
            }

            switch model.phase {
            case .finished:
                Button("Start chatting", action: onDone).buttonStyle(GlassPrimaryButtonStyle())
            case .failed(let why):
                Label(why, systemImage: "exclamationmark.triangle").foregroundStyle(.red).font(.callout)
                Button("Try again") { model.start() }.buttonStyle(GlassPrimaryButtonStyle())
                Button(showLog ? "Hide details" : "Show details") { showLog.toggle() }.buttonStyle(.borderless)
            case .waitingForTools:
                Button("I've installed them") { model.start() }.buttonStyle(GlassSecondaryButtonStyle())
            default:
                Button(showLog ? "Hide details" : "Show details") { showLog.toggle() }.buttonStyle(.borderless)
            }
            if showLog {
                ScrollView {
                    Text(model.log.suffix(80).joined(separator: "\n"))
                        .font(.system(.caption, design: .monospaced)).textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .frame(height: 180)
                .padding(10)
                .glassCard(14)
                Button("Copy details") { Clipboard.copy(model.log.joined(separator: "\n")) }.buttonStyle(.borderless)
            }
        }
    }

    private func row(_ s: SetupModel.Step) -> some View {
        let done = s.rawValue < model.step.rawValue || model.phase == .finished
        let active = s == model.step && model.phase != .finished
        return HStack(spacing: 12) {
            ZStack {
                if done { Image(systemName: "checkmark.circle.fill").foregroundStyle(.green) }
                else if active, case .failed = model.phase { Image(systemName: "xmark.circle.fill").foregroundStyle(.red) }
                else if active { ProgressView().controlSize(.small) }
                else { Image(systemName: s.icon).foregroundStyle(.tertiary) }
            }
            .font(.title3).frame(width: 26)
            Text(s.title).fontWeight(active ? .semibold : .regular).foregroundStyle(done || active ? .primary : .secondary)
            Spacer()
        }
    }
}
#endif
