import SwiftUI

private enum GallerySegOpt: String, CaseIterable, CustomStringConvertible { case day, week, month; var description: String { rawValue.capitalized } }

struct ComponentGallery: View {
    @State private var refineText: String = ""
    @State private var showRefine: Bool = false
    @State private var showSwap: Bool = false
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Space.xl) {
                MyonText("Typography", style: .title2)
                VStack(alignment: .leading, spacing: Space.sm) {
                    MyonText("Display", style: .display)
                    MyonText("Title 1", style: .title1)
                    MyonText("Body", style: .body)
                    MyonText("Secondary", style: .body, color: ColorsToken.Text.secondary)
                }

                MyonText("Buttons", style: .title2)
                VStack(spacing: Space.md) {
                    MyonButton("Primary") {}
                    MyonButton("Secondary", style: .secondary) {}
                    MyonButton("Ghost", style: .ghost) {}
                    MyonButton("Destructive", style: .destructive) {}
                }

                MyonText("Prompt Bar & Quick Actions", style: .title2)
                VStack(spacing: Space.md) {
                    StatefulPreviewWrapper("") { b in
                        AgentPromptBar(text: b, placeholder: "Ask anything") {}
                            .frame(maxWidth: 680)
                    }
                    HStack(spacing: Space.md) {
                        QuickActionCard(title: "Start exercise", icon: "play.fill") {}
                        QuickActionCard(title: "Analyze my progress", icon: "chart.bar") {}
                    }
                }

                MyonText("Cards", style: .title2)
                SurfaceCard {
                    VStack(alignment: .leading, spacing: Space.sm) {
                        MyonText("Session Plan", style: .headline)
                        MyonText("Upper body focus today.", style: .subheadline, color: ColorsToken.Text.secondary)
                        HStack(spacing: Space.sm) {
                            MyonButton("Accept") {}
                            MyonButton("Reject", style: .secondary) {}
                        }
                    }
                }

                MyonText("Canvas Cards", style: .title2)
                VStack(alignment: .leading, spacing: Space.md) {
                    // Agent Stream
                    let steps: [AgentStreamStep] = [
                        AgentStreamStep(kind: .thinking, durationMs: 500),
                        AgentStreamStep(kind: .info, text: "Thought for 3s", durationMs: 900),
                        AgentStreamStep(kind: .lookup, text: "Looking up profile", durationMs: 800),
                        AgentStreamStep(kind: .result, text: "Found profile", durationMs: 700)
                    ]
                    let stream = CanvasCardModel(
                        type: .analysis_task,
                        title: "Planning Program",
                        data: .agentStream(steps: steps),
                        width: .full,
                        actions: [CardAction(kind: "explain", label: "Explain", style: .secondary)],
                        menuItems: [CardAction(kind: "copy", label: "Copy")])
                    AgentStreamCard(model: stream)

                    // List card with options
                    let opts = [
                        ListOption(title: "Bench Press", subtitle: "4 sets of 8-10 reps", iconSystemName: "dumbbell"),
                        ListOption(title: "Pull Ups", subtitle: "3 sets to failure", iconSystemName: "figure.pullup")
                    ]
                    let listCard = CanvasCardModel(
                        type: .session_plan,
                        title: "Upper Body Focus",
                        data: .list(options: opts),
                        width: .full,
                        actions: [CardAction(kind: "apply", label: "Apply", style: .primary), CardAction(kind: "dismiss", label: "Dismiss", style: .secondary)],
                        menuItems: [CardAction(kind: "pin", label: "Pin"), CardAction(kind: "report", label: "Report")])
                    ListCardWithExpandableOptions(model: listCard, options: opts)

                    // Clarify questions
                    let qs = [
                        ClarifyQuestion(text: "What days can you train?", options: ["2", "3", "4", "5"], type: .single_choice),
                        ClarifyQuestion(text: "Any equipment limitations?", type: .text)
                    ]
                    let clarify = CanvasCardModel(type: .analysis_task, title: "A few questions", data: .clarifyQuestions(qs), width: .full, actions: [CardAction(kind: "submit_answers", label: "Submit", style: .primary)])
                    ClarifyQuestionsCard(model: clarify)

                    // Overview
                    let overviewModel = CanvasCardModel(type: .summary, title: "Your Program", data: .routineOverview(split: "PPL", days: 3, notes: "Balanced push/pull/legs."), width: .full, actions: [CardAction(kind: "refine", label: "Refine", style: .secondary)])
                    RoutineOverviewCard(model: overviewModel)

                    // Proposal group header
                    let header = CanvasCardModel(
                        type: .summary,
                        title: "Agent Actions",
                        data: .groupHeader(title: "Agent Actions"),
                        width: .full,
                        actions: [CardAction(kind: "accept_all", label: "Accept all", style: .primary), CardAction(kind: "reject_all", label: "Reject all", style: .secondary)])
                    ProposalGroupHeader(model: header, onAction: { _ in })
                }

                MyonText("Inputs", style: .title2)
                VStack(spacing: Space.md) {
                    StatefulPreviewWrapper("") { b in
                        MyonTextField("Email", text: b, placeholder: "you@example.com")
                    }
                    StatefulPreviewWrapper(true) { b in
                        MyonToggle("Sensors", isOn: b, subtitle: "Use Apple Watch for HR")
                    }
                    StatefulPreviewWrapper(8.0) { b in
                        MyonSlider("RIR", value: b, in: 0...5, step: 1) { String(Int($0)) }
                    }
                    StatefulPreviewWrapper(GallerySegOpt.week) { b in
                        MyonSegmented("Range", options: GallerySegOpt.allCases, selection: b)
                    }
                }

                MyonText("Aux", style: .title2)
                HStack(spacing: Space.md) {
                    StatusTag("Info")
                    StatusTag("OK", kind: .success)
                    StatusTag("Warn", kind: .warning)
                    StatusTag("Error", kind: .error)
                }
                HStack(spacing: Space.md) {
                    Avatar(initials: "VA")
                    Spinner()
                    Icon("star.fill", size: .lg)
                }

                MyonText("Banners & Toast", style: .title2)
                VStack(spacing: Space.md) {
                    Banner(title: "Session saved", message: "Your workout has been stored.", kind: .success)
                    Banner(title: "Network issue", message: "We’ll retry in the background.", kind: .warning)
                }
                Toast("Action completed")

                MyonText("Sheets", style: .title2)
                HStack(spacing: Space.md) {
                    MyonButton("Show Refine") { showRefine = true }
                    MyonButton("Show Swap", style: .secondary) { showSwap = true }
                }
                .sheet(isPresented: $showRefine) {
                    RefineSheet(text: $refineText) { _ in showRefine = false }
                }
                .sheet(isPresented: $showSwap) {
                    SwapSheet { _, _ in showSwap = false }
                }

                MyonText("Canvas Demo", style: .title2)
                let demo: [CanvasCardModel] = [
                    CanvasCardModel(type: .summary, title: "Today", subtitle: "Upper body", data: .text("Upper body focus today.")),
                    CanvasCardModel(type: .visualization, title: "Squat 6m", subtitle: "Volume", data: .visualization(title: "Squat", subtitle: "6 months")),
                    CanvasCardModel(type: .coach_proposal, title: "Increase load +2.5 kg", data: .suggestion(title: "Adjust Load", rationale: "RIR ≤ 1 last set")),
                    CanvasCardModel(type: .session_plan, lane: .workout, title: "Session Plan", data: .sessionPlan(exercises: [
                        PlanExercise(name: "Bench Press", sets: 4),
                        PlanExercise(name: "Seated Row", sets: 4)
                    ])),
                    CanvasCardModel(type: .analysis_task, title: "Instruction", data: .chat(lines: ["Analyze squats last 6 months", "Show volume trend"]))
                ]
                CanvasGridView(cards: demo, columns: 2)
            }
            .padding(InsetsToken.screen)
        }
        .navigationTitle("Components")
    }
}

#if DEBUG
struct ComponentGallery_Previews: PreviewProvider {
    static var previews: some View {
        NavigationView { ComponentGallery() }
    }
}
#endif


