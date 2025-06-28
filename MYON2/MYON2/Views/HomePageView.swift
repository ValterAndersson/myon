import SwiftUI

struct HomePageView: View {
    var onLogout: (() -> Void)? = nil
    @StateObject private var workoutManager = ActiveWorkoutManager.shared
    @State private var showingActiveWorkout = false

    var body: some View {
        ZStack(alignment: .bottom) {
            TabView {
                HomeDashboardView()
                    .tabItem {
                        Image(systemName: "house.fill")
                        Text("Home")
                    }
                WorkoutsView()
                    .tabItem {
                        Image(systemName: "figure.strengthtraining.traditional")
                        Text("Workouts")
                    }
                StrengthOSView()
                    .tabItem {
                        Image(systemName: "brain")
                        Text("StrengthOS")
                    }
                DevicesView()
                    .tabItem {
                        Image(systemName: "dot.radiowaves.left.and.right")
                        Text("Devices")
                    }
                MoreView(onLogout: onLogout)
                    .tabItem {
                        Image(systemName: "ellipsis.circle")
                        Text("More")
                    }
            }
            
            // Minimized workout bar
            if workoutManager.isWorkoutActive && workoutManager.isMinimized {
                MinimizedWorkoutBar(
                    duration: workoutManager.workoutDuration,
                    onExpand: {
                        workoutManager.setMinimized(false)
                        showingActiveWorkout = true
                    }
                )
                .padding(.bottom, 49) // Height of tab bar
            }
        }
        .fullScreenCover(isPresented: $showingActiveWorkout) {
            ActiveWorkoutView(isExpandedFromMinimized: true)
        }
    }
}

// MARK: - Minimized Workout Bar
struct MinimizedWorkoutBar: View {
    let duration: TimeInterval
    let onExpand: () -> Void
    @State private var isAnimating = false
    
    var body: some View {
        HStack {
            // Workout indicator
            HStack(spacing: 8) {
                Circle()
                    .fill(Color.red)
                    .frame(width: 8, height: 8)
                    .scaleEffect(isAnimating ? 1.2 : 1.0)
                    .opacity(isAnimating ? 0.6 : 1.0)
                    .animation(.easeInOut(duration: 1).repeatForever(autoreverses: true), value: isAnimating)
                    .onAppear { isAnimating = true }
                
                Text("Active Workout")
                    .font(.subheadline)
                    .fontWeight(.medium)
            }
            
            Spacer()
            
            // Timer
            Text(formatDuration(duration))
                .font(.subheadline.monospacedDigit())
                .fontWeight(.semibold)
            
            Spacer()
            
            // Expand button
            Button(action: onExpand) {
                Image(systemName: "chevron.up")
                    .font(.caption)
                    .foregroundColor(.blue)
                    .padding(8)
                    .background(Color.blue.opacity(0.1))
                    .clipShape(Circle())
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(Color(.systemBackground))
                .shadow(color: .black.opacity(0.1), radius: 8, x: 0, y: -2)
        )
        .padding(.horizontal, 16)
    }
    
    private func formatDuration(_ duration: TimeInterval) -> String {
        let hours = Int(duration) / 3600
        let minutes = (Int(duration) % 3600) / 60
        let seconds = Int(duration) % 60
        
        if hours > 0 {
            return String(format: "%d:%02d:%02d", hours, minutes, seconds)
        } else {
            return String(format: "%d:%02d", minutes, seconds)
        }
    }
}