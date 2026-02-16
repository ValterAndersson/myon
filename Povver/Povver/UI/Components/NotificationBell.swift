import SwiftUI

struct NotificationBell: View {
    let badgeCount: Int
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            ZStack(alignment: .topTrailing) {
                Image(systemName: "bell.fill")
                    .font(.system(size: 20))
                    .foregroundColor(Color.textPrimary)
                    .frame(width: 44, height: 44)

                if badgeCount > 0 {
                    Text(badgeCount > 9 ? "9+" : "\(badgeCount)")
                        .font(.system(size: 11, weight: .bold))
                        .foregroundColor(.white)
                        .frame(minWidth: 18, minHeight: 18)
                        .background(Color.accent)
                        .clipShape(Circle())
                        .offset(x: 6, y: -2)
                }
            }
        }
        .buttonStyle(PlainButtonStyle())
    }
}
