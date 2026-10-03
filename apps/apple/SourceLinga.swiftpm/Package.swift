// swift-tools-version: 5.9
// The iPhone / iPad app. Open this folder (SourceLinga.swiftpm) in Xcode 15+ on a Mac, or in Swift Playgrounds
// on an iPad, then press Run. The Mac app is built from the same Swift files by apps/mac/build.sh.
import PackageDescription
import AppleProductTypes

let package = Package(
    name: "Source Linga",
    platforms: [.iOS("17.0")],
    products: [
        .iOSApplication(
            name: "Source Linga",
            targets: ["App"],
            bundleIdentifier: "com.sourcelinga.app",
            teamIdentifier: "",
            displayVersion: "1.1.0",
            bundleVersion: "1",
            appIcon: .asset("AppIcon"),
            accentColor: .presetColor(.indigo),
            supportedDeviceFamilies: [.pad, .phone],
            supportedInterfaceOrientations: [
                .portrait,
                .landscapeRight,
                .landscapeLeft,
                .portraitUpsideDown(.when(deviceFamilies: [.pad]))
            ],
            capabilities: [
                .localNetwork(purposeString: "Source Linga talks to the AI running on your Mac over your Wi-Fi.",
                              bonjourServiceTypes: ["_sourcelinga._tcp"])
            ],
            appCategory: .productivity
        )
    ],
    targets: [
        .executableTarget(name: "App", path: "Sources/App", resources: [.process("Resources")])
    ]
)
