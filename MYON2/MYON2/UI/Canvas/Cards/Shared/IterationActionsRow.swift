import SwiftUI

/// Iteration action bar with quick actions and Coach menu
/// Used by both SessionPlanCard (for whole workout) and RoutineSummaryCard (per workout day)
public struct IterationActionsRow: View {
    let context: Context
    let onAdjust: (String) -> Void  // Instruction to send to agent
    
    public enum Context {
        case workout  // Single workout (SessionPlanCard)
        case routineDay(index: Int, title: String)  // Workout day in routine
    }
    
    public var body: some View {
        HStack(spacing: Space.sm) {
            // Visible: 2 most common quick actions
            iterationPill("Shorter", icon: "minus.circle") {
                switch context {
                case .workout:
                    onAdjust("Make this session shorter - reduce total sets or exercises")
                case .routineDay(let index, let title):
                    onAdjust("Make Day \(index + 1) (\(title)) shorter - reduce exercises or sets")
                }
            }
            
            iterationPill("Harder", icon: "flame") {
                switch context {
                case .workout:
                    onAdjust("Make this session more challenging - increase intensity or volume")
                case .routineDay(let index, let title):
                    onAdjust("Make Day \(index + 1) (\(title)) harder - more volume or intensity")
                }
            }
            
            // Coach menu: Less common actions
            Menu {
                Button {
                    switch context {
                    case .workout:
                        onAdjust("Change the muscle focus of this workout")
                    case .routineDay(let index, let title):
                        onAdjust("Change the muscle focus of Day \(index + 1) (\(title))")
                    }
                } label: {
                    Label("Swap Focus", systemImage: "arrow.triangle.2.circlepath")
                }
                
                Button {
                    switch context {
                    case .workout:
                        onAdjust("Regenerate this workout plan with different exercises")
                    case .routineDay(let index, let title):
                        onAdjust("Regenerate Day \(index + 1) (\(title)) with different exercises")
                    }
                } label: {
                    Label("Regenerate", systemImage: "sparkles")
                }
                
                Divider()
                
                Button {
                    onAdjust("Balance the volume more evenly across muscle groups")
                } label: {
                    Label("Balance Volume", systemImage: "scale.3d")
                }
                
                Button {
                    onAdjust("Adjust for limited equipment availability")
                } label: {
                    Label("Equipment Limits", systemImage: "wrench.adjustable")
                }
            } label: {
                HStack(spacing: 4) {
                    Image(systemName: "sparkles")
                        .font(.system(size: 11))
                    Text("Coach")
                        .font(.system(size: 12, weight: .medium))
                    Image(systemName: "chevron.down")
                        .font(.system(size: 8))
                }
                .foregroundColor(ColorsToken.Brand.primary)
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .background(ColorsToken.Brand.primary.opacity(0.1))
                .clipShape(Capsule())
            }
            
            Spacer()
        }
    }
    
    private func iterationPill(_ label: String, icon: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 4) {
                Image(systemName: icon)
                    .font(.system(size: 11))
                Text(label)
                    .font(.system(size: 12, weight: .medium))
            }
            .foregroundColor(ColorsToken.Text.primary)
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(ColorsToken.Background.secondary)
            .clipShape(Capsule())
        }
        .buttonStyle(PlainButtonStyle())
    }
}
