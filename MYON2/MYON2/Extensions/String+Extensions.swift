import Foundation

extension String {
    func matches(_ pattern: String) -> Bool {
        return self.range(of: pattern, options: .regularExpression) != nil
    }
}

extension Date {
    func relativeTimeString() -> String {
        let now = Date()
        let components = Calendar.current.dateComponents([.year, .month, .day, .hour, .minute], from: self, to: now)
        
        // Future dates
        if self > now {
            return "Just now"
        }
        
        // Minutes
        if let minutes = components.minute, let hours = components.hour, let days = components.day,
           let months = components.month, let years = components.year {
            
            // Less than 1 minute
            if years == 0 && months == 0 && days == 0 && hours == 0 && minutes < 1 {
                return "Just now"
            }
            
            // 1-59 minutes
            if years == 0 && months == 0 && days == 0 && hours == 0 && minutes < 60 {
                return minutes == 1 ? "1 minute" : "\(minutes) minutes"
            }
            
            // 1-23 hours
            if years == 0 && months == 0 && days == 0 && hours < 24 {
                return hours == 1 ? "1 hour" : "\(hours) hours"
            }
            
            // 1-6 days
            if years == 0 && months == 0 && days < 7 {
                return days == 1 ? "Yesterday" : "\(days) days"
            }
            
            // More than 6 days - show date
            let formatter = DateFormatter()
            
            // Same year - show month and day
            if years == 0 {
                formatter.dateFormat = "MMM d"
                return formatter.string(from: self)
            }
            
            // Different year - show full date
            formatter.dateFormat = "MMM d, yyyy"
            return formatter.string(from: self)
        }
        
        return "Unknown"
    }
} 