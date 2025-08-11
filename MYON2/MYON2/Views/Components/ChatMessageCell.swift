import UIKit
#if canImport(Down)
import Down
#endif

class ChatMessageCell: UICollectionViewCell {
    // MARK: - Properties
    private let bubbleView = UIView()
    private let messageLabel = UILabel()
    private let imageView = UIImageView()
    private let timestampLabel = UILabel()
    private let statusIndicator = UIImageView()
    
    private var bubbleLeadingConstraint: NSLayoutConstraint!
    private var bubbleTrailingConstraint: NSLayoutConstraint!
    private var imageHeightConstraint: NSLayoutConstraint!
    private var bubbleMaxWidthConstraint: NSLayoutConstraint!
    
    // MARK: - Init
    override init(frame: CGRect) {
        super.init(frame: frame)
        setupUI()
    }
    
    required init?(coder: NSCoder) {
        super.init(coder: coder)
        setupUI()
    }
    
    // MARK: - Setup
    private func setupUI() {
        contentView.backgroundColor = .clear
        
        // Bubble view
        bubbleView.layer.cornerRadius = 18
        bubbleView.translatesAutoresizingMaskIntoConstraints = false
        
        // Message label
        messageLabel.numberOfLines = 0
        messageLabel.font = .systemFont(ofSize: 15)
        messageLabel.translatesAutoresizingMaskIntoConstraints = false
        messageLabel.setContentCompressionResistancePriority(.required, for: .vertical)
        messageLabel.setContentHuggingPriority(.defaultLow, for: .horizontal)
        
        // Image view
        imageView.contentMode = .scaleAspectFill
        imageView.clipsToBounds = true
        imageView.layer.cornerRadius = 12
        imageView.translatesAutoresizingMaskIntoConstraints = false
        imageView.isHidden = true
        
        // Timestamp
        timestampLabel.font = .systemFont(ofSize: 11)
        timestampLabel.textColor = .secondaryLabel
        timestampLabel.translatesAutoresizingMaskIntoConstraints = false
        
        // Status indicator
        statusIndicator.contentMode = .scaleAspectFit
        statusIndicator.translatesAutoresizingMaskIntoConstraints = false
        
        // Add subviews
        contentView.addSubview(bubbleView)
        bubbleView.addSubview(messageLabel)
        bubbleView.addSubview(imageView)
        contentView.addSubview(timestampLabel)
        contentView.addSubview(statusIndicator)
        
        // Constraints
        bubbleLeadingConstraint = bubbleView.leadingAnchor.constraint(equalTo: contentView.leadingAnchor, constant: 16)
        bubbleTrailingConstraint = bubbleView.trailingAnchor.constraint(equalTo: contentView.trailingAnchor, constant: -16)
        imageHeightConstraint = imageView.heightAnchor.constraint(equalToConstant: 0)
        bubbleMaxWidthConstraint = bubbleView.widthAnchor.constraint(lessThanOrEqualToConstant: 280)
        
        NSLayoutConstraint.activate([
            bubbleView.topAnchor.constraint(equalTo: contentView.topAnchor, constant: 4),
            bubbleMaxWidthConstraint,
            
            messageLabel.topAnchor.constraint(equalTo: bubbleView.topAnchor, constant: 12),
            messageLabel.leadingAnchor.constraint(equalTo: bubbleView.leadingAnchor, constant: 16),
            messageLabel.trailingAnchor.constraint(equalTo: bubbleView.trailingAnchor, constant: -16),
            
            imageView.topAnchor.constraint(equalTo: messageLabel.bottomAnchor, constant: 8),
            imageView.leadingAnchor.constraint(equalTo: messageLabel.leadingAnchor),
            imageView.trailingAnchor.constraint(equalTo: messageLabel.trailingAnchor),
            imageHeightConstraint,
            imageView.bottomAnchor.constraint(equalTo: bubbleView.bottomAnchor, constant: -12),
            
            timestampLabel.topAnchor.constraint(equalTo: bubbleView.bottomAnchor, constant: 4),
            timestampLabel.bottomAnchor.constraint(equalTo: contentView.bottomAnchor, constant: -4),
            
            statusIndicator.centerYAnchor.constraint(equalTo: timestampLabel.centerYAnchor),
            statusIndicator.widthAnchor.constraint(equalToConstant: 16),
            statusIndicator.heightAnchor.constraint(equalToConstant: 16)
        ])
    }
    
    // MARK: - Configuration
    func configure(with message: ChatMessage) {
        // Set message content
        switch message.content {
        case .text(let text):
            // Apply basic markdown formatting
            let attributedText = applyMarkdownFormatting(to: text)
            messageLabel.attributedText = attributedText
            messageLabel.isHidden = false
            imageView.isHidden = true
            imageHeightConstraint.constant = 0
            
        case .image(let data, let caption):
            messageLabel.text = caption
            messageLabel.isHidden = caption == nil
            imageView.image = UIImage(data: data)
            imageView.isHidden = false
            imageHeightConstraint.constant = 200
            
        case .error(let error):
            messageLabel.text = error
            messageLabel.isHidden = false
            imageView.isHidden = true
            imageHeightConstraint.constant = 0
            
        default:
            break
        }
        
        // Clear existing timestamp constraints
        timestampLabel.removeFromSuperview()
        contentView.addSubview(timestampLabel)
        timestampLabel.translatesAutoresizingMaskIntoConstraints = false
        
        // Configure bubble appearance based on author
        switch message.author {
        case .user:
            bubbleView.backgroundColor = .systemBlue
            messageLabel.textColor = .white
            
            // Align to right
            bubbleLeadingConstraint.isActive = false
            bubbleTrailingConstraint.isActive = true
            // Limit user bubble width so it's compact (WhatsApp-like)
            bubbleMaxWidthConstraint.constant = 320
            bubbleMaxWidthConstraint.isActive = true
            
            // Timestamp on right (aligned with bubble right edge)
            NSLayoutConstraint.activate([
                timestampLabel.topAnchor.constraint(equalTo: bubbleView.bottomAnchor, constant: 4),
                timestampLabel.trailingAnchor.constraint(equalTo: bubbleView.trailingAnchor),
                timestampLabel.bottomAnchor.constraint(equalTo: contentView.bottomAnchor, constant: -4)
            ])
            
            // Status on left of timestamp
            statusIndicator.removeFromSuperview()
            contentView.addSubview(statusIndicator)
            statusIndicator.translatesAutoresizingMaskIntoConstraints = false
            NSLayoutConstraint.activate([
                statusIndicator.trailingAnchor.constraint(equalTo: timestampLabel.leadingAnchor, constant: -4),
                statusIndicator.centerYAnchor.constraint(equalTo: timestampLabel.centerYAnchor),
                statusIndicator.widthAnchor.constraint(equalToConstant: 16),
                statusIndicator.heightAnchor.constraint(equalToConstant: 16)
            ])
            
        case .agent:
            // Full-width, left-aligned assistant response without background for document-like feel
            bubbleView.backgroundColor = .clear
            messageLabel.textColor = .label
            
            // Full width: pin to both sides and remove max-width limit
            bubbleLeadingConstraint.isActive = true
            bubbleTrailingConstraint.isActive = true
            bubbleMaxWidthConstraint.isActive = false
            
            // Timestamp on left (aligned with bubble left edge)
            NSLayoutConstraint.activate([
                timestampLabel.topAnchor.constraint(equalTo: bubbleView.bottomAnchor, constant: 4),
                timestampLabel.leadingAnchor.constraint(equalTo: bubbleView.leadingAnchor),
                timestampLabel.bottomAnchor.constraint(equalTo: contentView.bottomAnchor, constant: -4)
            ])
            
            statusIndicator.isHidden = true
            
        case .system:
            bubbleView.backgroundColor = .tertiarySystemBackground
            messageLabel.textColor = .secondaryLabel
            messageLabel.font = .systemFont(ofSize: 14)
            
            // Center align
            bubbleLeadingConstraint.isActive = true
            bubbleTrailingConstraint.isActive = true
            bubbleMaxWidthConstraint.isActive = false
            
            timestampLabel.isHidden = true
            statusIndicator.isHidden = true
        }
        
        // Set timestamp
        let formatter = DateFormatter()
        formatter.timeStyle = .short
        timestampLabel.text = formatter.string(from: message.timestamp)
        
        // Set status indicator
        configureStatus(message.status)
    }
    
    private func applyMarkdownFormatting(to text: String) -> NSAttributedString {
        let attributedString = NSMutableAttributedString(string: text)
        
        // Set base attributes
        let paragraphStyle = NSMutableParagraphStyle()
        paragraphStyle.lineSpacing = 2
        paragraphStyle.paragraphSpacing = 6
        
        attributedString.addAttributes([
            .font: UIFont.systemFont(ofSize: 15),
            .paragraphStyle: paragraphStyle
        ], range: NSRange(location: 0, length: attributedString.length))
        
        // Bold text: **text** or __text__
        let boldPattern = "(\\*\\*|__)(.+?)(\\*\\*|__)"
        if let boldRegex = try? NSRegularExpression(pattern: boldPattern, options: []) {
            let matches = boldRegex.matches(in: attributedString.string, options: [], range: NSRange(location: 0, length: attributedString.length))
            for match in matches.reversed() {
                let matchRange = match.range
                let textRange = match.range(at: 2)
                
                if let substringRange = Range(textRange, in: attributedString.string) {
                    let boldText = String(attributedString.string[substringRange])
                    attributedString.replaceCharacters(in: matchRange, with: boldText)
                    
                    let newRange = NSRange(location: matchRange.location, length: boldText.count)
                    attributedString.addAttribute(.font, value: UIFont.boldSystemFont(ofSize: 17), range: newRange)
                }
            }
        }
        
        // Italic text: *text* or _text_ (but not ** or __)
        let italicPattern = "(?<!\\*)(\\*|_)(?!\\*|_)(.+?)(?<!\\*)(\\*|_)(?!\\*|_)"
        if let italicRegex = try? NSRegularExpression(pattern: italicPattern, options: []) {
            let matches = italicRegex.matches(in: attributedString.string, options: [], range: NSRange(location: 0, length: attributedString.length))
            
            for match in matches.reversed() {
                let matchRange = match.range
                let textRange = match.range(at: 2)
                
                if let substringRange = Range(textRange, in: attributedString.string) {
                    let italicText = String(attributedString.string[substringRange])
                    attributedString.replaceCharacters(in: matchRange, with: italicText)
                    
                    let newRange = NSRange(location: matchRange.location, length: italicText.count)
                    attributedString.addAttribute(.font, value: UIFont.italicSystemFont(ofSize: 17), range: newRange)
                }
            }
        }
        
        // Normalize bullets to '-' to avoid odd characters from streams
        let normalized = attributedString.string
            .replacingOccurrences(of: "\u{2022}", with: "-") // •
            .replacingOccurrences(of: "\u{2023}", with: "-") // ‣
        attributedString.mutableString.setString(normalized)

        // Process list items line by line
        let lines = attributedString.string.components(separatedBy: "\n")
        var currentLocation = 0
        
        for (index, line) in lines.enumerated() {
            let trimmedLine = line.trimmingCharacters(in: .whitespaces)
            
            // Calculate indentation level (2 spaces = 1 level)
            let leadingSpaces = line.prefix(while: { $0 == " " || $0 == "\t" }).count
            let indentLevel = leadingSpaces / 2
            
            // Handle bullet lists (* or -)
            if trimmedLine.hasPrefix("* ") || trimmedLine.hasPrefix("- ") {
                // Find the bullet position
                if let bulletIndex = line.firstIndex(where: { $0 == "*" || $0 == "-" }) {
                    let bulletPosition = line.distance(from: line.startIndex, to: bulletIndex)
                    let absoluteBulletPosition = currentLocation + bulletPosition
                    
                    // Replace with appropriate bullet based on indent level
                    let bulletChar = indentLevel == 0 ? "- " : "  - "
                    let bulletRange = NSRange(location: absoluteBulletPosition, length: 1)
                    attributedString.replaceCharacters(in: bulletRange, with: bulletChar)
                    
                    // Apply list paragraph style with proper indentation
                    let lineLength = line.count + (bulletChar.count - 1) // Adjust for bullet replacement
                    let lineRange = NSRange(location: currentLocation, length: lineLength)
                    
                    let listParagraphStyle = NSMutableParagraphStyle()
                    listParagraphStyle.firstLineHeadIndent = CGFloat(indentLevel * 16)
                    listParagraphStyle.headIndent = CGFloat(indentLevel * 16 + 18)
                    listParagraphStyle.lineSpacing = 1.5
                    listParagraphStyle.paragraphSpacing = 4
                    
                    attributedString.addAttribute(.paragraphStyle, value: listParagraphStyle, range: lineRange)
                }
            }
            // Handle numbered lists (1., 2., etc.)
            else if let match = trimmedLine.range(of: "^\\d+\\.\\s", options: .regularExpression) {
                let numberEnd = trimmedLine.distance(from: trimmedLine.startIndex, to: match.upperBound)
                
                // Apply list paragraph style with proper indentation
                let lineRange = NSRange(location: currentLocation, length: line.count)
                
                let listParagraphStyle = NSMutableParagraphStyle()
                listParagraphStyle.firstLineHeadIndent = CGFloat(indentLevel * 16)
                listParagraphStyle.headIndent = CGFloat(indentLevel * 16 + 22) // More indent for numbers
                listParagraphStyle.lineSpacing = 1.5
                listParagraphStyle.paragraphSpacing = 4
                
                attributedString.addAttribute(.paragraphStyle, value: listParagraphStyle, range: lineRange)
                
                // Make the number bold
                let numberRange = NSRange(location: currentLocation + leadingSpaces, length: numberEnd)
                attributedString.addAttribute(.font, value: UIFont.boldSystemFont(ofSize: 15), range: numberRange)
            }
            
            // Update location for next line (add 1 for newline character, except for last line)
            currentLocation += line.count
            if index < lines.count - 1 {
                currentLocation += 1
            }
        }
        
        return attributedString
    }
    
    private func configureStatus(_ status: MessageStatus) {
        switch status {
        case .sending:
            statusIndicator.image = UIImage(systemName: "clock")
            statusIndicator.tintColor = .secondaryLabel
        case .sent:
            statusIndicator.image = UIImage(systemName: "checkmark")
            statusIndicator.tintColor = .secondaryLabel
        case .delivered:
            statusIndicator.image = UIImage(systemName: "checkmark.circle.fill")
            statusIndicator.tintColor = .systemBlue
        case .failed:
            statusIndicator.image = UIImage(systemName: "exclamationmark.circle.fill")
            statusIndicator.tintColor = .systemRed
        case .streaming:
            statusIndicator.image = UIImage(systemName: "ellipsis")
            statusIndicator.tintColor = .systemBlue
        }
    }
    
    // MARK: - Reuse
    override func prepareForReuse() {
        super.prepareForReuse()
        messageLabel.text = nil
        imageView.image = nil
        timestampLabel.text = nil
        statusIndicator.image = nil
    }
} 