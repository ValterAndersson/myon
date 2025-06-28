import SwiftUI

// MARK: - Dashboard Stat Row
struct StatRow: View {
    let title: String
    let value: String

    var body: some View {
        HStack {
            Text(title)
            Spacer()
            Text(value)
                .bold()
        }
    }
}

#if DEBUG
struct StatRow_Previews: PreviewProvider {
    static var previews: some View {
        StatRow(title: "Workouts", value: "5")
            .previewLayout(.sizeThatFits)
            .padding()
    }
}
#endif
