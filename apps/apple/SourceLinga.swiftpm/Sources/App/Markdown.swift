import SwiftUI

/// A small Markdown renderer for answers: paragraphs, headings, lists, quotes, tables (as text) and code blocks.
/// Inline styles (bold, italic, `code`, links) use Apple's own Markdown parser.
enum MDBlock: Hashable {
    case paragraph(String)
    case heading(Int, String)
    case bullet([String])
    case numbered([String])
    case quote(String)
    case code(lang: String, text: String)
    case rule
}

enum Markdown {
    static func blocks(_ src: String) -> [MDBlock] {
        var out: [MDBlock] = []
        let lines = src.components(separatedBy: "\n")
        var i = 0
        func isBullet(_ l: String) -> Bool { l.range(of: #"^\s*[-*•]\s+"#, options: .regularExpression) != nil }
        func isNumber(_ l: String) -> Bool { l.range(of: #"^\s*\d+[.)]\s+"#, options: .regularExpression) != nil }
        func strip(_ l: String, _ pattern: String) -> String { l.replacingOccurrences(of: pattern, with: "", options: .regularExpression) }
        while i < lines.count {
            let l = lines[i]
            let trimmed = l.trimmingCharacters(in: .whitespaces)
            if trimmed.hasPrefix("```") {
                let lang = String(trimmed.dropFirst(3)).trimmingCharacters(in: .whitespaces)
                var code: [String] = []
                i += 1
                while i < lines.count, !lines[i].trimmingCharacters(in: .whitespaces).hasPrefix("```") { code.append(lines[i]); i += 1 }
                i += 1
                out.append(.code(lang: lang, text: code.joined(separator: "\n")))
                continue
            }
            if trimmed.isEmpty { i += 1; continue }
            if let m = trimmed.range(of: #"^#{1,4}\s+"#, options: .regularExpression) {
                let level = trimmed[m].filter { $0 == "#" }.count
                out.append(.heading(level, String(trimmed[m.upperBound...]))); i += 1; continue
            }
            if trimmed == "---" || trimmed == "***" { out.append(.rule); i += 1; continue }
            if trimmed.hasPrefix(">") {
                var q: [String] = []
                while i < lines.count, lines[i].trimmingCharacters(in: .whitespaces).hasPrefix(">") {
                    q.append(strip(lines[i], #"^\s*>\s?"#)); i += 1
                }
                out.append(.quote(q.joined(separator: "\n"))); continue
            }
            if isBullet(l) || isNumber(l) {
                let numbered = isNumber(l)
                var items: [String] = []
                while i < lines.count {
                    let x = lines[i]
                    if numbered ? isNumber(x) : isBullet(x) {
                        items.append(strip(x, numbered ? #"^\s*\d+[.)]\s+"# : #"^\s*[-*•]\s+"#))
                    } else if !items.isEmpty, x.hasPrefix("  "), !x.trimmingCharacters(in: .whitespaces).isEmpty {
                        items[items.count - 1] += "\n" + x.trimmingCharacters(in: .whitespaces)
                    } else { break }
                    i += 1
                }
                out.append(numbered ? .numbered(items) : .bullet(items)); continue
            }
            var p: [String] = []
            while i < lines.count {
                let x = lines[i], t = x.trimmingCharacters(in: .whitespaces)
                if t.isEmpty || t.hasPrefix("```") || t.hasPrefix("#") || t.hasPrefix(">") || isBullet(x) || isNumber(x) { break }
                p.append(x); i += 1
            }
            if p.isEmpty { p.append(l); i += 1 }
            out.append(.paragraph(p.joined(separator: "\n")))
        }
        return out
    }

    static func inline(_ s: String) -> AttributedString {
        (try? AttributedString(markdown: s, options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace)))
            ?? AttributedString(s)
    }
}

struct MarkdownView: View {
    let text: String
    var streaming = false

    var body: some View {
        let blocks = Markdown.blocks(text)
        VStack(alignment: .leading, spacing: 10) {
            ForEach(Array(blocks.enumerated()), id: \.offset) { i, b in
                block(b, last: i == blocks.count - 1)
            }
        }
        .textSelection(.enabled)
    }

    private func caret(_ last: Bool) -> Text {
        streaming && last ? Text(" ▍").foregroundColor(.secondary) : Text("")
    }

    @ViewBuilder private func block(_ b: MDBlock, last: Bool) -> some View {
        switch b {
        case .paragraph(let s):
            (Text(Markdown.inline(s)) + caret(last)).fixedSize(horizontal: false, vertical: true)
        case .heading(let level, let s):
            Text(Markdown.inline(s)).font(level == 1 ? .title2.bold() : level == 2 ? .title3.bold() : .headline)
                .padding(.top, 4)
        case .bullet(let items), .numbered(let items):
            let numbered: Bool = { if case .numbered = b { return true }; return false }()
            VStack(alignment: .leading, spacing: 6) {
                ForEach(Array(items.enumerated()), id: \.offset) { n, item in
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        Text(numbered ? "\(n + 1)." : "•").foregroundStyle(.secondary).monospacedDigit()
                            .frame(minWidth: numbered ? 18 : 10, alignment: .trailing)
                        (Text(Markdown.inline(item)) + caret(last && n == items.count - 1))
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }
        case .quote(let s):
            HStack(spacing: 10) {
                RoundedRectangle(cornerRadius: 2).fill(.quaternary).frame(width: 3)
                Text(Markdown.inline(s)).foregroundStyle(.secondary)
            }
        case .code(let lang, let code):
            CodeBlock(lang: lang, code: code)
        case .rule:
            Divider()
        }
    }
}

struct CodeBlock: View {
    let lang: String
    let code: String
    @State private var copied = false

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text(lang.isEmpty ? "code" : lang).font(.caption.monospaced()).foregroundStyle(.secondary)
                Spacer()
                Button {
                    Clipboard.copy(code)
                    copied = true
                    DispatchQueue.main.asyncAfter(deadline: .now() + 1.4) { copied = false }
                } label: {
                    Label(copied ? "Copied" : "Copy", systemImage: copied ? "checkmark" : "doc.on.doc").font(.caption)
                }
                .buttonStyle(.borderless)
            }
            .padding(.horizontal, 12).padding(.vertical, 7)
            Divider()
            ScrollView(.horizontal, showsIndicators: false) {
                Text(code).font(.system(.callout, design: .monospaced)).padding(12).textSelection(.enabled)
            }
        }
        .background(Theme.codeBackground, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).strokeBorder(.quaternary))
    }
}
