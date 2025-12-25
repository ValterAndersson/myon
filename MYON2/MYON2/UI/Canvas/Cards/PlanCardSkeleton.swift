import SwiftUI

/// Skeleton placeholder for plan card while loading.
/// Uses subtle pulsing (not shimmer) for a calm, premium feel.
struct PlanCardSkeleton: View {
    @State private var isPulsing = false
    
    var body: some View {
        VStack(alignment: .leading, spacing: Space.md) {
            // Header skeleton
            headerSkeleton
            
            // Divider
            Rectangle()
                .fill(ColorsToken.Separator.hairline)
                .frame(height: 1)
            
            // Exercise rows skeleton
            ForEach(0..<3, id: \.self) { _ in
                exerciseRowSkeleton
            }
            
            // Footer skeleton
            footerSkeleton
        }
        .padding(Space.md)
        .background(ColorsToken.Surface.card)
        .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.large))
        .shadowStyle(ShadowsToken.level1)
        .opacity(isPulsing ? 0.6 : 1.0)
        .onAppear {
            withAnimation(.easeInOut(duration: 1.0).repeatForever(autoreverses: true)) {
                isPulsing = true
            }
        }
    }
    
    // MARK: - Header
    
    private var headerSkeleton: some View {
        VStack(alignment: .leading, spacing: Space.xs) {
            HStack {
                // Title placeholder
                PlaceholderRect(height: 20, width: 140)
                
                Spacer()
                
                // Status badge placeholder
                PlaceholderRect(height: 20, width: 70)
                    .clipShape(Capsule())
            }
            
            // Summary line placeholder
            PlaceholderRect(height: 14, width: 220)
        }
    }
    
    // MARK: - Exercise Row
    
    private var exerciseRowSkeleton: some View {
        HStack {
            VStack(alignment: .leading, spacing: Space.xs) {
                // Exercise name
                PlaceholderRect(height: 16, width: CGFloat.random(in: 120...180))
                
                // Sets summary
                PlaceholderRect(height: 12, width: CGFloat.random(in: 80...120))
            }
            
            Spacer()
            
            // Chevron placeholder
            PlaceholderRect(height: 12, width: 12)
        }
        .padding(.vertical, Space.sm)
    }
    
    // MARK: - Footer
    
    private var footerSkeleton: some View {
        HStack(spacing: Space.sm) {
            // Action button placeholders
            PlaceholderRect(height: 28, width: 70)
                .clipShape(Capsule())
            
            PlaceholderRect(height: 28, width: 60)
                .clipShape(Capsule())
            
            Spacer()
        }
        .padding(.top, Space.sm)
    }
}

// MARK: - Placeholder Rectangle

private struct PlaceholderRect: View {
    let height: CGFloat
    let width: CGFloat
    
    var body: some View {
        RoundedRectangle(cornerRadius: 4)
            .fill(ColorsToken.Neutral.n200)
            .frame(width: width, height: height)
    }
}

// MARK: - Compact Progress Indicator

/// A compact progress indicator for use during agent work
struct AgentProgressIndicator: View {
    @ObservedObject var progressState: AgentProgressState
    
    var body: some View {
        if progressState.isActive {
            HStack(spacing: Space.sm) {
                ProgressView()
                    .scaleEffect(0.8)
                
                Text(progressState.currentStage.displayText)
                    .font(.system(size: 13))
                    .foregroundColor(ColorsToken.Text.secondary)
                
                Spacer()
            }
            .padding(.horizontal, Space.md)
            .padding(.vertical, Space.sm)
            .background(ColorsToken.Surface.editingRow.opacity(0.6))
            .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.small))
        }
    }
}

// MARK: - Preview

#Preview("Plan Card Skeleton") {
    VStack {
        PlanCardSkeleton()
            .padding()
        
        Spacer()
    }
    .background(ColorsToken.Background.primary)
}
