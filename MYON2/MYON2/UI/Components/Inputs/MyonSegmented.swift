import SwiftUI

public struct MyonSegmented<Option: Hashable & CustomStringConvertible>: View {
    private let title: String
    private let options: [Option]
    @Binding private var selection: Option

    public init(_ title: String, options: [Option], selection: Binding<Option>) {
        self.title = title
        self.options = options
        self._selection = selection
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: Space.xs) {
            MyonText(title, style: .subheadline, color: ColorsToken.Text.secondary)
            Picker(title, selection: $selection) {
                ForEach(options, id: \.self) { option in
                    SwiftUI.Text(option.description).tag(option)
                }
            }
            .pickerStyle(.segmented)
        }
    }
}

#if DEBUG
struct MyonSegmented_Previews: PreviewProvider {
    enum SegOpt: String, CaseIterable, CustomStringConvertible { case day, week, month; var description: String { rawValue.capitalized } }
    @State static var sel: SegOpt = .day
    static var previews: some View {
        StatefulPreviewWrapper(SegOpt.day) { binding in
            MyonSegmented("Range", options: SegOpt.allCases, selection: binding)
                .padding(InsetsToken.screen)
        }
    }
}
#endif


