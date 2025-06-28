import SwiftUI

struct DevicesView: View {
    var body: some View {
        VStack(spacing: 24) {
            Text("Devices")
                .font(.largeTitle).bold()
            Text("Pair and manage your sensors and devices here.")
                .foregroundColor(.secondary)
        }
        .padding()
    }
} 