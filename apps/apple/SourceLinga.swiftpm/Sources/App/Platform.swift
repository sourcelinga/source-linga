import SwiftUI
import WebKit
#if os(macOS)
import AppKit
import Carbon.HIToolbox
#else
import UIKit
#endif

enum Theme {
    #if os(macOS)
    static let codeBackground = Color(nsColor: .textBackgroundColor).opacity(0.6)
    static let userBubble = Color.primary
    static let field = Color(nsColor: .controlBackgroundColor)
    #else
    static let codeBackground = Color(uiColor: .secondarySystemBackground)
    static let userBubble = Color.primary
    static let field = Color(uiColor: .secondarySystemBackground)
    #endif
}

enum Clipboard {
    static func copy(_ s: String) {
        #if os(macOS)
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(s, forType: .string)
        #else
        UIPasteboard.general.string = s
        #endif
    }
}

/// The app's logo, from the app bundle (the Mac build) or the package resources (the iPhone build).
struct Logo: View {
    var size: CGFloat = 32
    var body: some View {
        Group {
            if let img = Logo.image { img.resizable().interpolation(.high) } else { Color.black }
        }
        .frame(width: size, height: size)
        .clipShape(RoundedRectangle(cornerRadius: size * 0.24, style: .continuous))
    }

    static let image: Image? = {
        #if SWIFT_PACKAGE
        let bundle = Bundle.module
        #else
        let bundle = Bundle.main
        #endif
        guard let url = bundle.url(forResource: "logo", withExtension: "png") else { return nil }
        #if os(macOS)
        return NSImage(contentsOf: url).map { Image(nsImage: $0) }
        #else
        return UIImage(contentsOfFile: url.path).map { Image(uiImage: $0) }
        #endif
    }()
}

// MARK: - The full tools (Improve, Workflows, Knowledge, Updates, Devices) are the Mac's web dashboard

struct WebTools: View {
    let base: URL
    let key: String?
    var body: some View { WebViewBox(url: base, key: key) }
}

#if os(macOS)
struct WebViewBox: NSViewRepresentable {
    let url: URL
    let key: String?
    func makeNSView(context: Context) -> WKWebView { makeWebView(url: url, key: key) }
    func updateNSView(_ v: WKWebView, context: Context) {}
}
#else
struct WebViewBox: UIViewRepresentable {
    let url: URL
    let key: String?
    func makeUIView(context: Context) -> WKWebView { makeWebView(url: url, key: key) }
    func updateUIView(_ v: WKWebView, context: Context) {}
}
#endif

private func makeWebView(url: URL, key: String?) -> WKWebView {
    let cfg = WKWebViewConfiguration()
    cfg.websiteDataStore = .nonPersistent()
    let web = WKWebView(frame: .zero, configuration: cfg)
    web.allowsBackForwardNavigationGestures = true
    if let key, let host = url.host,
       let cookie = HTTPCookie(properties: [.name: "sl_key", .value: key, .domain: host, .path: "/",
                                            .expires: Date().addingTimeInterval(3600 * 24 * 365)]) {
        cfg.websiteDataStore.httpCookieStore.setCookie(cookie) { web.load(URLRequest(url: url)) }
    } else {
        web.load(URLRequest(url: url))
    }
    return web
}

// MARK: - Mac only: global shortcut (⌥Space) and starting the AI engine

#if os(macOS)
final class HotKey {
    static let shared = HotKey()
    private var ref: EventHotKeyRef?
    private var handler: EventHandlerRef?
    var action: (() -> Void)?

    /// Option-Space from any app brings Source Linga forward with a new chat. Carbon hot keys need no
    /// Accessibility permission.
    func register() {
        guard ref == nil else { return }
        var spec = EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed))
        InstallEventHandler(GetApplicationEventTarget(), { _, _, _ in
            DispatchQueue.main.async { HotKey.shared.action?() }
            return noErr
        }, 1, &spec, nil, &handler)
        let id = EventHotKeyID(signature: OSType(0x534C4E47), id: 1)  // 'SLNG'
        RegisterEventHotKey(UInt32(kVK_Space), UInt32(optionKey), id, GetApplicationEventTarget(), 0, &ref)
    }

    func unregister() {
        if let ref { UnregisterEventHotKey(ref) }
        ref = nil
    }
}

enum Engine {
    static var appURL: URL? {
        let u = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Applications/Forge.app")
        return FileManager.default.fileExists(atPath: u.path) ? u : nil
    }
    static func start() {
        guard let u = appURL else { return }
        let cfg = NSWorkspace.OpenConfiguration()
        cfg.activates = false
        NSWorkspace.shared.openApplication(at: u, configuration: cfg)
    }
}
#endif
