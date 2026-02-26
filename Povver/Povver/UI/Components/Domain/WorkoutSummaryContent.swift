import SwiftUI

/// Pure rendering component for workout analytics.
/// All analytics are server-computed by analytics-calculator.js — no client calculation.
/// Used by both the post-workout completion flow and history detail screen.
struct WorkoutSummaryContent: View {
    let workout: Workout

    /// Optional callbacks for note editing (only wired up from history detail, not post-workout).
    var onEditWorkoutNote: (() -> Void)?
    var onEditExerciseNote: ((Int) -> Void)?

    private var weightUnit: WeightUnit { UserService.shared.weightUnit }

    private var durationMinutes: Int {
        Int(workout.endTime.timeIntervalSince(workout.startTime) / 60)
    }

    private var formattedDate: String {
        let fmt = DateFormatter()
        fmt.dateFormat = "EEEE, MMM d 'at' h:mm a"
        return fmt.string(from: workout.endTime)
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Space.xl) {
                headerSection
                workoutNoteRow
                statsRow
                muscleGroupSection
                intensitySection
                exerciseListSection
                Spacer(minLength: Space.xxl)
            }
        }
    }

    // MARK: - Header

    private var headerSection: some View {
        VStack(alignment: .leading, spacing: Space.xs) {
            Text(workout.displayName)
                .font(.system(size: 24, weight: .bold))
                .foregroundColor(Color.textPrimary)

            Text(formattedDate)
                .font(.system(size: 14))
                .foregroundColor(Color.textSecondary)
        }
        .padding(.horizontal, Space.lg)
        .padding(.top, Space.md)
    }

    // MARK: - Workout Note

    @ViewBuilder
    private var workoutNoteRow: some View {
        if let notes = workout.notes, !notes.isEmpty {
            Button {
                onEditWorkoutNote?()
            } label: {
                HStack(spacing: Space.sm) {
                    Image(systemName: "note.text")
                        .font(.system(size: 13))
                        .foregroundColor(Color.textTertiary)
                    Text(notes)
                        .font(.system(size: 14))
                        .foregroundColor(Color.textSecondary)
                        .lineLimit(1)
                    Spacer()
                    if onEditWorkoutNote != nil {
                        Image(systemName: "chevron.right")
                            .font(.system(size: 11, weight: .semibold))
                            .foregroundColor(Color.textTertiary)
                    }
                }
                .padding(.horizontal, Space.lg)
            }
            .buttonStyle(.plain)
            .disabled(onEditWorkoutNote == nil)
        }
    }

    // MARK: - Stats Row

    private var statsRow: some View {
        HStack(spacing: 0) {
            statCell(value: "\(workout.analytics.totalSets)", label: "Sets")
            statCell(value: "\(workout.analytics.totalReps)", label: "Reps")
            statCell(value: formatVolume(workout.analytics.totalWeight), label: "Volume (\(weightUnit.label))")
            statCell(value: "\(durationMinutes)", label: "Min")
        }
        .padding(.horizontal, Space.lg)
    }

    private func statCell(value: String, label: String) -> some View {
        VStack(spacing: Space.xxs) {
            Text(value)
                .font(.system(size: 22, weight: .bold).monospacedDigit())
                .foregroundColor(Color.textPrimary)
            Text(label)
                .font(.system(size: 12))
                .foregroundColor(Color.textSecondary)
        }
        .frame(maxWidth: .infinity)
    }

    // MARK: - Muscle Group Distribution

    @ViewBuilder
    private var muscleGroupSection: some View {
        let groups = topMuscleGroups(from: workout.analytics.setsPerMuscleGroup, limit: 6)
        if !groups.isEmpty {
            VStack(alignment: .leading, spacing: Space.sm) {
                Text("Muscle Groups")
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundColor(Color.textPrimary)

                let maxSets = groups.map(\.sets).max() ?? 1
                ForEach(groups, id: \.name) { group in
                    muscleGroupBar(name: group.name, sets: group.sets, max: maxSets)
                }
            }
            .padding(.horizontal, Space.lg)
        }
    }

    private func muscleGroupBar(name: String, sets: Int, max: Int) -> some View {
        HStack(spacing: Space.sm) {
            Text(name.replacingOccurrences(of: "_", with: " ").capitalized)
                .font(.system(size: 13))
                .foregroundColor(Color.textSecondary)
                .frame(width: 90, alignment: .trailing)

            GeometryReader { geo in
                let fraction = max > 0 ? CGFloat(sets) / CGFloat(max) : 0
                RoundedRectangle(cornerRadius: 4)
                    .fill(Color.accent)
                    .frame(width: geo.size.width * fraction)
            }
            .frame(height: 14)

            Text("\(sets)")
                .font(.system(size: 13).monospacedDigit())
                .foregroundColor(Color.textPrimary)
                .frame(width: 24, alignment: .trailing)
        }
    }

    // MARK: - Intensity

    @ViewBuilder
    private var intensitySection: some View {
        if let intensity = workout.analytics.intensity, intensity.hardSets > 0 {
            VStack(alignment: .leading, spacing: Space.sm) {
                Text("Intensity")
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundColor(Color.textPrimary)

                HStack(spacing: Space.lg) {
                    intensityMetric(
                        value: "\(intensity.hardSets)",
                        label: "Hard Sets",
                        caption: "RIR 0-3"
                    )
                    intensityMetric(
                        value: "\(intensity.lowRirSets)",
                        label: "Low RIR",
                        caption: "RIR 0-1"
                    )
                    if intensity.avgRelativeIntensity > 0 {
                        intensityMetric(
                            value: "\(Int(intensity.avgRelativeIntensity * 100))%",
                            label: "Avg Intensity",
                            caption: "% of e1RM"
                        )
                    }
                }
            }
            .padding(.horizontal, Space.lg)
        }
    }

    private func intensityMetric(value: String, label: String, caption: String) -> some View {
        VStack(spacing: Space.xxs) {
            Text(value)
                .font(.system(size: 20, weight: .bold).monospacedDigit())
                .foregroundColor(Color.textPrimary)
            Text(label)
                .font(.system(size: 12, weight: .medium))
                .foregroundColor(Color.textSecondary)
            Text(caption)
                .font(.system(size: 10))
                .foregroundColor(Color.textTertiary)
        }
        .frame(maxWidth: .infinity)
    }

    // MARK: - Exercise List

    @ViewBuilder
    private var exerciseListSection: some View {
        if workout.exercises.isEmpty {
            Text("No exercises recorded")
                .font(.system(size: 14))
                .foregroundColor(Color.textSecondary)
                .padding(.horizontal, Space.lg)
        } else {
            VStack(spacing: Space.sm) {
                ForEach(workout.exercises.indices, id: \.self) { index in
                    let exercise = workout.exercises[index]
                    ExerciseSection(
                        model: .readOnly(
                            id: exercise.id,
                            title: exercise.name,
                            indexLabel: "\(index + 1)",
                            subtitle: exerciseSubtitle(exercise)
                        )
                    ) {
                        if !exercise.sets.isEmpty {
                            SetTable(
                                sets: exercise.sets.toSetCellModels(weightUnit: weightUnit),
                                mode: .readOnly,
                                weightUnit: weightUnit.label
                            )
                        }
                        // Exercise note row
                        if let notes = exercise.notes, !notes.isEmpty {
                            Button {
                                onEditExerciseNote?(index)
                            } label: {
                                HStack(spacing: Space.xs) {
                                    Image(systemName: "note.text")
                                        .font(.system(size: 11))
                                        .foregroundColor(Color.textTertiary)
                                    Text(notes)
                                        .font(.system(size: 13))
                                        .foregroundColor(Color.textSecondary)
                                        .lineLimit(1)
                                    Spacer()
                                    if onEditExerciseNote != nil {
                                        Image(systemName: "chevron.right")
                                            .font(.system(size: 10, weight: .semibold))
                                            .foregroundColor(Color.textTertiary)
                                    }
                                }
                                .padding(.top, Space.xs)
                            }
                            .buttonStyle(.plain)
                            .disabled(onEditExerciseNote == nil)
                        }
                    }
                }
            }
            .padding(.horizontal, Space.lg)
        }
    }

    // MARK: - Helpers

    private func exerciseSubtitle(_ exercise: WorkoutExercise) -> String {
        let sets = exercise.analytics.totalSets
        let volume = exercise.analytics.totalWeight
        if volume > 0 {
            return "\(sets) sets · \(formatVolume(volume)) \(weightUnit.label)"
        }
        return "\(sets) sets"
    }

    private func formatVolume(_ weight: Double) -> String {
        let displayed = WeightFormatter.display(weight, unit: weightUnit)
        let rounded = WeightFormatter.roundForDisplay(displayed)
        if rounded == rounded.rounded() {
            return "\(Int(rounded))"
        }
        return String(format: "%.1f", rounded)
    }

    private struct MuscleGroupEntry {
        let name: String
        let sets: Int
    }

    private func topMuscleGroups(from map: [String: Int], limit: Int) -> [MuscleGroupEntry] {
        map.map { MuscleGroupEntry(name: $0.key, sets: $0.value) }
            .sorted { $0.sets > $1.sets }
            .prefix(limit)
            .map { $0 }
    }
}
