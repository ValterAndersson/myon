import Foundation
import UIKit

// MARK: - String Extensions
extension String {
    func matches(_ pattern: String) -> Bool {
        return self.range(of: pattern, options: .regularExpression) != nil
    }
    
    // MARK: - Email Validation
    var isValidEmail: Bool {
        let emailRegex = #"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"#
        return self.matches(emailRegex)
    }
    
    // MARK: - Password Validation
    var passwordStrength: PasswordStrength {
        return PasswordValidator.evaluate(self)
    }
    
    var hasMinimumLength: Bool { count >= 8 }
    var hasUppercase: Bool { matches("[A-Z]") }
    var hasLowercase: Bool { matches("[a-z]") }
    var hasNumber: Bool { matches("[0-9]") }
    var hasSpecialCharacter: Bool { matches("[^A-Za-z0-9]") }
}

// MARK: - Password Validation
enum PasswordStrength: CaseIterable {
    case weak, fair, good, strong
    
    var description: String {
        switch self {
        case .weak: return "Weak"
        case .fair: return "Fair" 
        case .good: return "Good"
        case .strong: return "Strong"
        }
    }
    
    var color: UIColor {
        switch self {
        case .weak: return .systemRed
        case .fair: return .systemOrange
        case .good: return .systemYellow
        case .strong: return .systemGreen
        }
    }
}

struct PasswordValidator {
    static func evaluate(_ password: String) -> PasswordStrength {
        var score = 0
        
        if password.hasMinimumLength { score += 1 }
        if password.hasUppercase { score += 1 }
        if password.hasLowercase { score += 1 }
        if password.hasNumber { score += 1 }
        if password.hasSpecialCharacter { score += 1 }
        
        switch score {
        case 0...1: return .weak
        case 2...3: return .fair
        case 4: return .good
        case 5: return .strong
        default: return .weak
        }
    }
    
    static func requirements(for password: String) -> [PasswordRequirement] {
        return [
            PasswordRequirement(text: "At least 8 characters", isValid: password.hasMinimumLength),
            PasswordRequirement(text: "Contains uppercase letter", isValid: password.hasUppercase),
            PasswordRequirement(text: "Contains lowercase letter", isValid: password.hasLowercase),
            PasswordRequirement(text: "Contains number", isValid: password.hasNumber),
            PasswordRequirement(text: "Contains special character", isValid: password.hasSpecialCharacter)
        ]
    }
}

// MARK: - Haptic Feedback Manager
class HapticFeedbackManager {
    static let shared = HapticFeedbackManager()
    
    private let lightImpact = UIImpactFeedbackGenerator(style: .light)
    private let mediumImpact = UIImpactFeedbackGenerator(style: .medium)
    private let heavyImpact = UIImpactFeedbackGenerator(style: .heavy)
    private let notificationFeedback = UINotificationFeedbackGenerator()
    private let selectionFeedback = UISelectionFeedbackGenerator()
    
    private init() {
        // Prepare generators for better performance
        lightImpact.prepare()
        mediumImpact.prepare()
        heavyImpact.prepare()
        notificationFeedback.prepare()
        selectionFeedback.prepare()
    }
    
    func light() {
        guard UIDevice.current.userInterfaceIdiom == .phone else { return }
        lightImpact.impactOccurred()
        lightImpact.prepare() // Prepare for next use
    }
    
    func medium() {
        guard UIDevice.current.userInterfaceIdiom == .phone else { return }
        mediumImpact.impactOccurred()
        mediumImpact.prepare()
    }
    
    func heavy() {
        guard UIDevice.current.userInterfaceIdiom == .phone else { return }
        heavyImpact.impactOccurred()
        heavyImpact.prepare()
    }
    
    func success() {
        guard UIDevice.current.userInterfaceIdiom == .phone else { return }
        notificationFeedback.notificationOccurred(.success)
        notificationFeedback.prepare()
    }
    
    func error() {
        guard UIDevice.current.userInterfaceIdiom == .phone else { return }
        notificationFeedback.notificationOccurred(.error)
        notificationFeedback.prepare()
    }
    
    func warning() {
        guard UIDevice.current.userInterfaceIdiom == .phone else { return }
        notificationFeedback.notificationOccurred(.warning)
        notificationFeedback.prepare()
    }
    
    func selection() {
        guard UIDevice.current.userInterfaceIdiom == .phone else { return }
        selectionFeedback.selectionChanged()
        selectionFeedback.prepare()
    }
}

// MARK: - Design Constants
struct AuthDesignConstants {
    static let cardCornerRadius: CGFloat = 24
    static let cardShadowRadius: CGFloat = 8
    static let inputCornerRadius: CGFloat = 12
    static let buttonHeight: CGFloat = 50
    static let socialButtonHeight: CGFloat = 52
    static let defaultPadding: CGFloat = 24
    static let sectionSpacing: CGFloat = 24
    static let minimumHeaderHeight: CGFloat = 200
    static let animationDuration: Double = 0.2
    static let springAnimationResponse: Double = 0.5
    static let springAnimationDamping: Double = 0.8
    static let focusDelay: Double = 0.5
}

// MARK: - Date Extensions (existing)
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