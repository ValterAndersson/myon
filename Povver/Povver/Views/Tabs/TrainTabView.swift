import SwiftUI

/// Train Tab - Workout execution hub
/// Routes to FocusModeWorkoutScreen with proper loading gate to prevent flash
struct TrainTabView: View {
    @StateObject private var workoutService = FocusModeWorkoutService.shared
    
    /// Loading state for active workout check
    @State private var isCheckingActiveWorkout = true
    @State private var hasActiveWorkout = false
    
    var body: some View {
        Group {
            if isCheckingActiveWorkout {
                // Lightweight loading state during active workout check
                loadingView
            } else {
                // FocusModeWorkoutScreen handles both:
                // - Start screen (no active workout)
                // - Resume/active workout view (has active workout)
                FocusModeWorkoutScreen()
            }
        }
        .task {
            await checkForActiveWorkout()
        }
    }
    
    /// Lightweight loading view
    private var loadingView: some View {
        VStack(spacing: Space.md) {
            ProgressView()
                .progressViewStyle(.circular)
            Text("Loading...")
                .font(.system(size: 14))
                .foregroundColor(Color.textSecondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.bg)
    }
    
    /// Check for active workout on appear
    /// This gates the first paint to prevent flashing the wrong screen
    private func checkForActiveWorkout() async {
        // Skip network call if service already has workout state (prefetched or resumed)
        if workoutService.workout != nil {
            hasActiveWorkout = true
            isCheckingActiveWorkout = false
            return
        }

        // Brief check - FocusModeWorkoutScreen will also check,
        // but this prevents the flash
        do {
            let activeWorkout = try await workoutService.getActiveWorkout()
            hasActiveWorkout = activeWorkout != nil
        } catch {
            // On error, show start screen (FocusModeWorkoutScreen handles this)
            hasActiveWorkout = false
        }

        // Gate complete - show the actual screen
        isCheckingActiveWorkout = false
    }
}

#if DEBUG
struct TrainTabView_Previews: PreviewProvider {
    static var previews: some View {
        NavigationStack {
            TrainTabView()
        }
    }
}
#endif
