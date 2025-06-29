import SwiftUI

struct TimeZonePickerView: View {
    @Binding var selectedTimeZone: String
    @Environment(\.dismiss) private var dismiss
    @State private var searchText = ""
    
    // Group timezones by region for better organization
    private var groupedTimeZones: [String: [TimeZone]] {
        let allTimeZones = TimeZone.knownTimeZoneIdentifiers.compactMap { TimeZone(identifier: $0) }
        
        var grouped: [String: [TimeZone]] = [:]
        
        for timeZone in allTimeZones {
            let components = timeZone.identifier.split(separator: "/")
            let region = String(components.first ?? "Other")
            
            if grouped[region] == nil {
                grouped[region] = []
            }
            grouped[region]?.append(timeZone)
        }
        
        // Sort timezones within each region
        for region in grouped.keys {
            grouped[region]?.sort { $0.identifier < $1.identifier }
        }
        
        return grouped
    }
    
    // Common time zones for quick access
    private let commonTimeZones = [
        "Europe/Helsinki",
        "Europe/Stockholm",
        "Europe/London",
        "Europe/Paris",
        "Europe/Berlin",
        "America/New_York",
        "America/Chicago",
        "America/Denver",
        "America/Los_Angeles",
        "Asia/Tokyo",
        "Asia/Shanghai",
        "Australia/Sydney"
    ]
    
    private var filteredTimeZones: [(String, [TimeZone])] {
        if searchText.isEmpty {
            return groupedTimeZones.sorted { $0.key < $1.key }
        } else {
            var filtered: [String: [TimeZone]] = [:]
            
            for (region, zones) in groupedTimeZones {
                let filteredZones = zones.filter { zone in
                    zone.identifier.localizedCaseInsensitiveContains(searchText) ||
                    formatTimeZoneName(zone).localizedCaseInsensitiveContains(searchText)
                }
                
                if !filteredZones.isEmpty {
                    filtered[region] = filteredZones
                }
            }
            
            return filtered.sorted { $0.key < $1.key }
        }
    }
    
    var body: some View {
        List {
            if searchText.isEmpty {
                // Show common time zones section when not searching
                Section(header: Text("Common Time Zones")) {
                    ForEach(commonTimeZones, id: \.self) { identifier in
                        if let timeZone = TimeZone(identifier: identifier) {
                            TimeZoneRow(
                                timeZone: timeZone,
                                isSelected: selectedTimeZone == identifier,
                                onSelect: {
                                    selectedTimeZone = identifier
                                    dismiss()
                                }
                            )
                        }
                    }
                }
            }
            
            // All time zones grouped by region
            ForEach(filteredTimeZones, id: \.0) { region, zones in
                Section(header: Text(region)) {
                    ForEach(zones, id: \.identifier) { timeZone in
                        TimeZoneRow(
                            timeZone: timeZone,
                            isSelected: selectedTimeZone == timeZone.identifier,
                            onSelect: {
                                selectedTimeZone = timeZone.identifier
                                dismiss()
                            }
                        )
                    }
                }
            }
        }
        .navigationTitle("Select Time Zone")
        .navigationBarTitleDisplayMode(.inline)
        .searchable(text: $searchText, prompt: "Search time zones")
    }
    
    private func formatTimeZoneName(_ timeZone: TimeZone) -> String {
        let components = timeZone.identifier.split(separator: "/")
        let cityName = components.last?.replacingOccurrences(of: "_", with: " ") ?? timeZone.identifier
        
        let offset = timeZone.secondsFromGMT() / 3600
        let offsetString = offset >= 0 ? "+\(offset)" : "\(offset)"
        
        return "\(cityName) (GMT\(offsetString))"
    }
}

struct TimeZoneRow: View {
    let timeZone: TimeZone
    let isSelected: Bool
    let onSelect: () -> Void
    
    var body: some View {
        Button(action: onSelect) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text(cityName)
                        .foregroundColor(.primary)
                    
                    Text(timeZone.identifier)
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                
                Spacer()
                
                VStack(alignment: .trailing, spacing: 4) {
                    Text("GMT\(offsetString)")
                        .font(.system(.body, design: .monospaced))
                        .foregroundColor(.secondary)
                    
                    Text(currentTime)
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                
                if isSelected {
                    Image(systemName: "checkmark")
                        .foregroundColor(.accentColor)
                        .padding(.leading, 8)
                }
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
    
    private var cityName: String {
        let components = timeZone.identifier.split(separator: "/")
        return components.last?.replacingOccurrences(of: "_", with: " ") ?? timeZone.identifier
    }
    
    private var offsetString: String {
        let offset = timeZone.secondsFromGMT() / 3600
        let minutes = abs(timeZone.secondsFromGMT() % 3600) / 60
        
        if minutes == 0 {
            return offset >= 0 ? "+\(offset)" : "\(offset)"
        } else {
            let sign = offset >= 0 ? "+" : "-"
            return "\(sign)\(abs(offset)):\(String(format: "%02d", minutes))"
        }
    }
    
    private var currentTime: String {
        let formatter = DateFormatter()
        formatter.timeZone = timeZone
        formatter.timeStyle = .short
        return formatter.string(from: Date())
    }
}

#Preview {
    NavigationView {
        TimeZonePickerView(selectedTimeZone: .constant("Europe/Helsinki"))
    }
} 