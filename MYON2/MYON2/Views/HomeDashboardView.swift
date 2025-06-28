import SwiftUI

struct HomeDashboardView: View {
    var body: some View {
        VStack(spacing: 24) {
            Text("Dashboard")
                .font(.largeTitle).bold()
            Text("Welcome! Your stats and quick actions will appear here.")
                .foregroundColor(.secondary)
        }
        .padding()
    }
} 