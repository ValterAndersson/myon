import SwiftUI

/// Main routines list view - shows all user routines with active routine highlighted
struct RoutinesListView: View {
    @StateObject private var viewModel = RoutinesViewModel()
    @State private var showingCreateSheet = false
    @State private var selectedRoutine: Routine?
    
    var body: some View {
        NavigationStack {
            Group {
                if viewModel.isLoading && viewModel.routines.isEmpty {
                    loadingView
                } else if viewModel.routines.isEmpty {
                    emptyStateView
                } else {
                    routinesList
                }
            }
            .navigationTitle("Routines")
            .toolbar {
                ToolbarItem(placement: .primaryAction) {
                    Button(action: { showingCreateSheet = true }) {
                        Image(systemName: "plus")
                            .font(.system(size: IconSizeToken.md, weight: .medium))
                    }
                }
            }
            .sheet(isPresented: $showingCreateSheet) {
                RoutineEditView(mode: .create) { newRoutine in
                    Task {
                        await viewModel.createRoutine(newRoutine)
                    }
                }
            }
            .sheet(item: $selectedRoutine) { routine in
                RoutineDetailView(routine: routine) {
                    Task { await viewModel.loadRoutines() }
                }
            }
            .refreshable {
                await viewModel.loadRoutines()
            }
            .task {
                await viewModel.loadRoutines()
            }
            .alert("Error", isPresented: .constant(viewModel.error != nil)) {
                Button("OK") { viewModel.error = nil }
            } message: {
                Text(viewModel.error ?? "")
            }
        }
    }
    
    private var loadingView: some View {
        VStack(spacing: Space.lg) {
            ProgressView()
            Text("Loading routines...")
                .font(TypographyToken.body)
                .foregroundColor(ColorsToken.Text.secondary)
        }
    }
    
    private var emptyStateView: some View {
        VStack(spacing: Space.xl) {
            Image(systemName: "figure.run.circle")
                .font(.system(size: 64))
                .foregroundColor(ColorsToken.Neutral.n400)
            
            VStack(spacing: Space.sm) {
                Text("No Routines Yet")
                    .font(TypographyToken.title2)
                    .foregroundColor(ColorsToken.Text.primary)
                
                Text("Create a routine to organize your workouts into a structured program.")
                    .font(TypographyToken.body)
                    .foregroundColor(ColorsToken.Text.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, Space.xl)
            }
            
            Button(action: { showingCreateSheet = true }) {
                Label("Create Routine", systemImage: "plus")
                    .font(TypographyToken.button)
            }
            .buttonStyle(.borderedProminent)
            .tint(ColorsToken.Brand.primary)
        }
        .padding(Space.xl)
    }
    
    private var routinesList: some View {
        List {
            // Active routine section
            if let activeRoutine = viewModel.activeRoutine {
                Section {
                    RoutineRowView(
                        routine: activeRoutine,
                        isActive: true,
                        templates: viewModel.templatesForRoutine(activeRoutine)
                    )
                    .contentShape(Rectangle())
                    .onTapGesture {
                        selectedRoutine = activeRoutine
                    }
                } header: {
                    Label("Active Routine", systemImage: "checkmark.circle.fill")
                        .font(TypographyToken.footnote)
                        .foregroundColor(ColorsToken.Brand.primary)
                }
            }
            
            // Other routines
            let otherRoutines = viewModel.routines.filter { $0.id != viewModel.activeRoutine?.id }
            if !otherRoutines.isEmpty {
                Section {
                    ForEach(otherRoutines) { routine in
                        RoutineRowView(
                            routine: routine,
                            isActive: false,
                            templates: viewModel.templatesForRoutine(routine)
                        )
                        .contentShape(Rectangle())
                        .onTapGesture {
                            selectedRoutine = routine
                        }
                        .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                            Button(role: .destructive) {
                                Task { await viewModel.deleteRoutine(routine) }
                            } label: {
                                Label("Delete", systemImage: "trash")
                            }
                            
                            Button {
                                Task { await viewModel.setActiveRoutine(routine) }
                            } label: {
                                Label("Set Active", systemImage: "checkmark.circle")
                            }
                            .tint(ColorsToken.Brand.primary)
                        }
                    }
                } header: {
                    Text("Other Routines")
                        .font(TypographyToken.footnote)
                        .foregroundColor(ColorsToken.Text.secondary)
                }
            }
        }
        .listStyle(.insetGrouped)
    }
}

// MARK: - Routine Row View

struct RoutineRowView: View {
    let routine: Routine
    let isActive: Bool
    let templates: [WorkoutTemplate]
    
    var body: some View {
        VStack(alignment: .leading, spacing: Space.sm) {
            // Header
            HStack {
                Text(routine.name)
                    .font(TypographyToken.headline)
                    .foregroundColor(ColorsToken.Text.primary)
                
                if isActive {
                    Image(systemName: "checkmark.circle.fill")
                        .font(.system(size: IconSizeToken.sm))
                        .foregroundColor(ColorsToken.Brand.primary)
                }
                
                Spacer()
                
                Text("\(routine.frequency)x/week")
                    .font(TypographyToken.caption)
                    .foregroundColor(ColorsToken.Text.secondary)
                    .padding(.horizontal, Space.sm)
                    .padding(.vertical, Space.xxs)
                    .background(ColorsToken.Neutral.n100)
                    .cornerRadius(CornerRadiusToken.small)
            }
            
            // Description
            if let description = routine.description, !description.isEmpty {
                Text(description)
                    .font(TypographyToken.subheadline)
                    .foregroundColor(ColorsToken.Text.secondary)
                    .lineLimit(2)
            }
            
            // Workouts preview
            if !templates.isEmpty {
                HStack(spacing: Space.sm) {
                    ForEach(templates.prefix(3)) { template in
                        TemplateChipView(template: template)
                    }
                    
                    if templates.count > 3 {
                        Text("+\(templates.count - 3)")
                            .font(TypographyToken.caption)
                            .foregroundColor(ColorsToken.Text.secondary)
                    }
                }
            } else {
                Text("No workouts added")
                    .font(TypographyToken.caption)
                    .foregroundColor(ColorsToken.Text.muted)
                    .italic()
            }
        }
        .padding(.vertical, Space.xs)
    }
}

// MARK: - Template Chip View

struct TemplateChipView: View {
    let template: WorkoutTemplate
    
    var body: some View {
        Text(template.name)
            .font(TypographyToken.caption)
            .foregroundColor(ColorsToken.Text.primary)
            .padding(.horizontal, Space.sm)
            .padding(.vertical, Space.xxs)
            .background(ColorsToken.Brand.accent100)
            .cornerRadius(CornerRadiusToken.small)
            .lineLimit(1)
    }
}

// MARK: - Preview

#Preview {
    RoutinesListView()
}
