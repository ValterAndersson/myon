import SwiftUI

struct StreamOverlay: View {
    let status: String
    let isThinking: Bool
    let events: [StreamEvent]
    
    @State private var animationRotation: Double = 0
    
    var body: some View {
        ZStack(alignment: .topLeading) {
            Color.clear
                .ignoresSafeArea()
            VStack(alignment: .leading, spacing: Space.xs) {
                let items = Array(events.suffix(50))
                ForEach(items.indices, id: \.self) { idx in
                    let event = items[idx]
                    HStack(alignment: .firstTextBaseline, spacing: Space.xs) {
                        Image(systemName: icon(for: event))
                            .font(.system(size: 12))
                            .foregroundColor(ColorsToken.Text.secondary)
                            .rotationEffect(rotation(for: event))
                            .animation(animation(for: event), value: animationRotation)
                        Text(text(for: event))
                            .font(.footnote)
                            .foregroundColor(ColorsToken.Text.secondary)
                            .textSelection(.disabled)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }
            .padding(.top, Space.lg)
            .padding(.horizontal, Space.lg)
            .allowsHitTesting(false)
        }
        .onAppear {
            if isThinking {
                withAnimation {
                    animationRotation = 360
                }
            }
        }
        .onChange(of: isThinking) { newValue in
            if newValue {
                withAnimation {
                    animationRotation = 360
                }
            } else {
                animationRotation = 0
            }
        }
    }
    
    private func icon(for event: StreamEvent) -> String {
        switch event.eventType {
        case .some(.userPrompt): return "person"
        case .some(.thinking): return "gearshape"
        case .some(.thought): return "lightbulb"
        case .some(.toolRunning): return "bolt"
        case .some(.toolComplete): return "checkmark.square"
        case .some(.agentResponse): return "text.bubble"
        default: return event.iconName
        }
    }
    
    private func rotation(for event: StreamEvent) -> Angle {
        if event.eventType == .thinking { return .degrees(animationRotation) }
        return .zero
    }
    
    private func animation(for event: StreamEvent) -> Animation? {
        if event.eventType == .thinking { return Animation.linear(duration: 1.6).repeatForever(autoreverses: false) }
        return nil
    }
    
    private func text(for event: StreamEvent) -> String {
        return event.displayText
    }
}
