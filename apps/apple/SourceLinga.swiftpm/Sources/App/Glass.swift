import SwiftUI

// MARK: - Liquid Glass
//
// On macOS 26 / iOS 26 and newer every glass surface is Apple's real Liquid Glass (`glassEffect`), so it
// refracts and reacts to touch like the system's own controls. Older systems get a close imitation built
// from the system materials plus a specular rim, so the app looks the same family everywhere.

extension Theme {
    /// The one accent colour: a calm, saturated blue-violet that reads on light and dark glass.
    static let accent = Color(red: 0.33, green: 0.40, blue: 1.0)
    static let accent2 = Color(red: 0.62, green: 0.36, blue: 1.0)
    static let accentGradient = LinearGradient(colors: [accent, accent2], startPoint: .topLeading, endPoint: .bottomTrailing)
}

extension View {
    /// A Liquid Glass surface in `shape`. `tint` colours the glass (for primary buttons and your own messages);
    /// `interactive` makes it flex and glow under the pointer or finger (iOS/macOS 26+).
    @ViewBuilder
    func glass<S: Shape>(_ shape: S, tint: Color? = nil, interactive: Bool = false) -> some View {
        if #available(macOS 26.0, iOS 26.0, *) {
            self.glassEffect(Glass.regular.tint(tint).interactive(interactive), in: shape)
        } else {
            self.modifier(GlassFallback(shape: shape, tint: tint))
        }
    }

    /// Glass for a whole card (rounded rectangle with Apple's continuous corners).
    func glassCard(_ radius: CGFloat = 18, tint: Color? = nil, interactive: Bool = false) -> some View {
        glass(RoundedRectangle(cornerRadius: radius, style: .continuous), tint: tint, interactive: interactive)
    }
}

private struct GlassFallback<S: Shape>: ViewModifier {
    let shape: S
    let tint: Color?
    @Environment(\.colorScheme) private var scheme

    func body(content: Content) -> some View {
        content
            .background {
                ZStack {
                    shape.fill(.ultraThinMaterial)
                    if let tint { shape.fill(tint.opacity(0.88)) }
                    // Specular rim: bright on the top-left edge, fading out, like light catching a glass lens.
                    shape.stroke(LinearGradient(colors: [.white.opacity(scheme == .dark ? 0.32 : 0.75),
                                                         .white.opacity(0.04),
                                                         .white.opacity(scheme == .dark ? 0.14 : 0.35)],
                                                startPoint: .topLeading, endPoint: .bottomTrailing),
                                 lineWidth: 1)
                }
                .shadow(color: .black.opacity(scheme == .dark ? 0.35 : 0.10), radius: 18, y: 8)
            }
    }
}

/// Groups neighbouring glass shapes so they blend into each other on macOS/iOS 26 (no-op before that).
struct GlassGroup<Content: View>: View {
    var spacing: CGFloat = 12
    @ViewBuilder var content: Content
    var body: some View {
        if #available(macOS 26.0, iOS 26.0, *) {
            GlassEffectContainer(spacing: spacing) { content }
        } else {
            content
        }
    }
}

/// The colourful light that glass needs behind it. Static gradients only (no blur, no animation), so it
/// costs nothing per frame while answers stream in.
struct LiquidBackdrop: View {
    @Environment(\.colorScheme) private var scheme
    var body: some View {
        let dark = scheme == .dark
        ZStack {
            (dark ? Color(red: 0.04, green: 0.05, blue: 0.09) : Color(red: 0.96, green: 0.97, blue: 1.0))
            RadialGradient(colors: [Theme.accent.opacity(dark ? 0.42 : 0.26), .clear],
                           center: UnitPoint(x: 0.12, y: 0.05), startRadius: 0, endRadius: 520)
            RadialGradient(colors: [Theme.accent2.opacity(dark ? 0.32 : 0.20), .clear],
                           center: UnitPoint(x: 0.95, y: 0.30), startRadius: 0, endRadius: 480)
            RadialGradient(colors: [Color(red: 0.2, green: 0.85, blue: 0.85).opacity(dark ? 0.20 : 0.16), .clear],
                           center: UnitPoint(x: 0.35, y: 1.05), startRadius: 0, endRadius: 520)
        }
        .ignoresSafeArea()
        .allowsHitTesting(false)
    }
}

/// A round glass icon button (send, stop, toolbar actions).
struct GlassIconButton: View {
    let systemImage: String
    var size: CGFloat = 34
    var prominent = false
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            Image(systemName: systemImage)
                .font(.system(size: size * 0.42, weight: .bold))
                .foregroundStyle(prominent ? Color.white : Color.primary)
                .frame(width: size, height: size)
                .contentShape(Circle())
        }
        .buttonStyle(.plain)
        .glass(Circle(), tint: prominent ? Theme.accent : nil, interactive: true)
    }
}

/// A wide primary button on glass ("Set up", "Pair", "Continue").
struct GlassPrimaryButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var enabled
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.headline)
            .foregroundStyle(.white)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 13)
            .contentShape(Capsule())
            .glass(Capsule(), tint: Theme.accent, interactive: true)
            .opacity(enabled ? (configuration.isPressed ? 0.85 : 1) : 0.45)
            .scaleEffect(configuration.isPressed ? 0.98 : 1)
            .animation(.easeOut(duration: 0.15), value: configuration.isPressed)
    }
}

/// A secondary button on clear glass.
struct GlassSecondaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.headline)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 13)
            .contentShape(Capsule())
            .glass(Capsule(), interactive: true)
            .opacity(configuration.isPressed ? 0.8 : 1)
    }
}
