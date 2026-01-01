import SwiftUI

struct ChatHomeEntry: View {
    var body: some View {
        Group {
            if let uid = AuthService.shared.currentUser?.uid {
                ChatHomeView(userId: uid)
            } else {
                EmptyState(title: "Not signed in", message: "Login to start chatting.")
            }
        }
    }
}

#if DEBUG
struct ChatHomeEntry_Previews: PreviewProvider {
    static var previews: some View { ChatHomeEntry() }
}
#endif


