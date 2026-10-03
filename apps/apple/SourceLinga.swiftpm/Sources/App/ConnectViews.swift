import SwiftUI

// MARK: - First run on iPhone/iPad (or another Mac): find the Mac and pair with its 6-digit code

struct ConnectView: View {
    @Environment(ChatStore.self) private var store
    @State private var discovery = Discovery()
    @State private var address = ""
    @State private var code = ""
    @State private var target: URL?
    @State private var targetName = ""
    @State private var busy = false
    @State private var error: String?
    @FocusState private var codeFocused: Bool

    var body: some View {
        ScrollView {
            VStack(spacing: 22) {
                Logo(size: 84).padding(10).glass(RoundedRectangle(cornerRadius: 32, style: .continuous)).padding(.top, 30)
                VStack(spacing: 6) {
                    Text("Connect to your Mac").font(.title.bold())
                    Text("Source Linga's AI runs on your Mac. This device sends it questions over your Wi-Fi.")
                        .multilineTextAlignment(.center).foregroundStyle(.secondary)
                }
                if target == nil { pickMac } else { enterCode }
                if let error { Label(error, systemImage: "exclamationmark.triangle").foregroundStyle(.red).font(.callout) }
            }
            .frame(maxWidth: 440)
            .padding(24)
            .frame(maxWidth: .infinity)
        }
        .background(LiquidBackdrop())
        .onAppear { discovery.start() }
        .onDisappear { discovery.stop() }
    }

    private var pickMac: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("MACS ON THIS WI-FI").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
            if discovery.found.isEmpty {
                HStack(spacing: 10) {
                    ProgressView().controlSize(.small)
                    Text("Looking… On the Mac, open Source Linga → Tools → Devices and switch on access.")
                        .font(.callout).foregroundStyle(.secondary)
                }
                .padding(14).frame(maxWidth: .infinity, alignment: .leading)
                .glassCard(16)
            }
            ForEach(discovery.found) { mac in
                Button {
                    Task {
                        busy = true; error = nil
                        if let url = await Discovery.resolve(mac.endpoint) {
                            target = url
                            targetName = mac.name.replacingOccurrences(of: "Source Linga on ", with: "")
                            codeFocused = true
                        } else { error = "Found \(mac.name) but couldn't connect. Try the address instead." }
                        busy = false
                    }
                } label: {
                    HStack {
                        Image(systemName: "laptopcomputer").font(.title3)
                        Text(mac.name.replacingOccurrences(of: "Source Linga on ", with: "")).fontWeight(.semibold)
                        Spacer()
                        if busy { ProgressView().controlSize(.small) } else { Image(systemName: "chevron.right").foregroundStyle(.tertiary) }
                    }
                    .padding(14)
                    .contentShape(Rectangle())
                    .glassCard(16, interactive: true)
                }
                .buttonStyle(.plain)
            }
            Text("OR TYPE THE ADDRESS").font(.caption.weight(.semibold)).foregroundStyle(.secondary).padding(.top, 8)
            HStack {
                TextField("e.g. 192.168.1.20 or my-mac.local", text: $address)
                    .textFieldStyle(.plain).autocorrectionDisabled()
                    #if os(iOS)
                    .textInputAutocapitalization(.never).keyboardType(.URL)
                    #endif
                    .onSubmit(useAddress)
                Button("Next", action: useAddress).bold().disabled(address.isEmpty)
            }
            .padding(14)
            .glassCard(16)
            Text("The address is shown on the Mac in Tools → Devices.").font(.caption).foregroundStyle(.secondary)
        }
    }

    private var enterCode: some View {
        VStack(spacing: 14) {
            Text("Pair with **\(targetName)**").font(.title3)
            Text("Type the 6-digit code shown on the Mac in Tools → Devices.").font(.callout).foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
            TextField("••••••", text: $code)
                .font(.system(size: 34, weight: .semibold, design: .monospaced))
                .multilineTextAlignment(.center)
                .textFieldStyle(.plain)
                .focused($codeFocused)
                #if os(iOS)
                .keyboardType(.numberPad).textContentType(.oneTimeCode)
                #endif
                .padding(14)
                .glassCard(18)
                .onChange(of: code) { if code.count == 6 { pair() } }
            Button(action: pair) {
                Group { if busy { ProgressView().tint(.white) } else { Text("Pair") } }
            }
            .buttonStyle(GlassPrimaryButtonStyle()).disabled(code.count != 6 || busy)
            Button("Choose another Mac") { target = nil; code = ""; error = nil }.buttonStyle(.borderless)
        }
    }

    private func useAddress() {
        guard let url = Endpoint.parse(address) else { error = "That doesn't look like an address."; return }
        busy = true; error = nil
        Task {
            do {
                let info = try await API(Endpoint(base: url, name: "", key: nil)).info()
                target = url
                targetName = info.computer ?? url.host ?? "Mac"
                codeFocused = true
            } catch { self.error = "No Source Linga at that address. Is the Mac awake, on this Wi-Fi, with device access on?" }
            busy = false
        }
    }

    private func pair() {
        guard let target, code.count == 6, !busy else { return }
        busy = true; error = nil
        Task {
            do {
                let r = try await API.pair(base: target, code: code)
                store.connect(Endpoint(base: target, name: r.computer, key: r.key))
            } catch {
                self.error = error.localizedDescription
                code = ""
            }
            busy = false
        }
    }
}

// MARK: - Settings

struct SettingsView: View {
    @Environment(ChatStore.self) private var store
    @Environment(\.dismiss) private var dismiss
    @AppStorage("hotkey") private var hotkey = true
    @State private var showConnect = false
    @State private var confirmRemove = false

    var body: some View {
        Form {
            Section("Connected to") {
                LabeledContent("Mac", value: store.endpoint?.isLocal == true ? "This Mac" : (store.computer.isEmpty ? store.endpoint?.name ?? "—" : store.computer))
                LabeledContent("Address", value: store.endpoint?.base.absoluteString ?? "—")
                LabeledContent("Status") { HStack { StatusDot(connection: store.connection); Text(store.statusLine) } }
                Button("Check again") { Task { await store.refresh() } }
            }
            #if os(macOS)
            Section("Mac") {
                Toggle("⌥Space opens Source Linga from any app", isOn: $hotkey)
                    .onChange(of: hotkey) { hotkey ? HotKey.shared.register() : HotKey.shared.unregister() }
                if store.endpoint?.isLocal == false {
                    Button("Use the AI on this Mac instead") { store.disconnect() }
                }
                if Engine.appURL != nil {
                    Button("Start the AI engine") { Engine.start() }
                    Button("Remove the AI engine from this Mac…", role: .destructive) { confirmRemove = true }
                }
                Button("Connect to the AI on another Mac…") { showConnect = true }
            }
            #else
            Section {
                Button("Disconnect and pair again", role: .destructive) { store.disconnect(); dismiss() }
            } footer: {
                Text("Your chats stay on the Mac; pairing again brings them back.")
            }
            #endif
            Section("About") {
                LabeledContent("Version", value: Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "2.0")
                Link("Instructions and source code", destination: URL(string: "https://github.com/sourcelinga/source-linga")!)
            }
        }
        .formStyle(.grouped)
        .navigationTitle("Settings")
        #if os(iOS)
        .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
        #else
        .frame(width: 460)
        .sheet(isPresented: $showConnect) {
            ConnectView().frame(width: 480, height: 600)
                .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Cancel") { showConnect = false } } }
        }
        .onChange(of: store.endpoint) { showConnect = false }
        .confirmationDialog("Remove the AI engine?", isPresented: $confirmRemove) {
            Button("Remove", role: .destructive) { Setup.uninstall(); Task { await store.refresh() } }
        } message: {
            Text("This stops the background service. Your chats and downloaded models are kept, so setting up again is quick. To delete the app too, drag Source Linga from Applications to the Bin.")
        }
        #endif
    }
}
