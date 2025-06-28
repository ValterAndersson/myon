import UIKit

class AgentActivityCell: UICollectionViewCell {
    // MARK: - Properties
    private let containerView = UIView()
    private let iconView = UIImageView()
    private let activityLabel = UILabel()
    private let activityIndicator = UIActivityIndicatorView(style: .medium)
    
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
        
        // Container now just acts as invisible wrapper (no bubble)
        containerView.backgroundColor = .clear
        containerView.layer.cornerRadius = 0
        containerView.translatesAutoresizingMaskIntoConstraints = false
        
        // Icon (hidden by default for clean log look)
        iconView.contentMode = .scaleAspectFit
        iconView.tintColor = .secondaryLabel
        iconView.translatesAutoresizingMaskIntoConstraints = false
        
        // Activity label (monospaced footnote for log style)
        activityLabel.font = UIFont.monospacedSystemFont(ofSize: 13, weight: .medium)
        activityLabel.textColor = .secondaryLabel
        activityLabel.numberOfLines = 0
        activityLabel.translatesAutoresizingMaskIntoConstraints = false
        
        // Activity indicator hidden; we rely on text now
        activityIndicator.hidesWhenStopped = true
        activityIndicator.translatesAutoresizingMaskIntoConstraints = false
        activityIndicator.stopAnimating()
        
        // Add subviews
        contentView.addSubview(containerView)
        containerView.addSubview(iconView)
        containerView.addSubview(activityLabel)
        containerView.addSubview(activityIndicator)
        
        // Constraints
        NSLayoutConstraint.activate([
            containerView.topAnchor.constraint(equalTo: contentView.topAnchor, constant: 4),
            containerView.leadingAnchor.constraint(equalTo: contentView.leadingAnchor, constant: 16),
            containerView.trailingAnchor.constraint(lessThanOrEqualTo: contentView.trailingAnchor, constant: -80),
            containerView.bottomAnchor.constraint(equalTo: contentView.bottomAnchor, constant: -4),
            
            iconView.leadingAnchor.constraint(equalTo: containerView.leadingAnchor, constant: 12),
            iconView.centerYAnchor.constraint(equalTo: containerView.centerYAnchor),
            iconView.widthAnchor.constraint(equalToConstant: 20),
            iconView.heightAnchor.constraint(equalToConstant: 20),
            
            activityIndicator.leadingAnchor.constraint(equalTo: iconView.trailingAnchor, constant: 8),
            activityIndicator.centerYAnchor.constraint(equalTo: containerView.centerYAnchor),
            
            // Always position text at the same location, regardless of icon visibility
            activityLabel.leadingAnchor.constraint(equalTo: containerView.leadingAnchor, constant: 40), // 12 + 20 + 8
            activityLabel.trailingAnchor.constraint(equalTo: containerView.trailingAnchor, constant: -12),
            activityLabel.topAnchor.constraint(equalTo: containerView.topAnchor, constant: 8),
            activityLabel.bottomAnchor.constraint(equalTo: containerView.bottomAnchor, constant: -8)
        ])
    }
    
    // MARK: - Configuration
    func configure(with activity: String) {
        activityLabel.text = activity
        
        // Always show icon for activity messages
        let icon = iconForActivity(activity) ?? UIImage(systemName: "gearshape")
        iconView.image = icon
        iconView.isHidden = false
        
        // Set appropriate color based on state
        let lower = activity.lowercased()
        if lower.contains("loaded") || lower.contains("complete") || lower.contains("verified") || lower.contains("found") || lower.contains("created") || lower.contains("updated") || lower.contains("deleted") || lower.contains("saved") || lower.contains("recalled") || lower.contains("activated") {
            iconView.tintColor = .systemGreen
        } else {
            iconView.tintColor = .secondaryLabel
        }
    }
    
    private func iconForActivity(_ activity: String) -> UIImage? {
        // Dynamic icon selection based on function name
        let lower = activity.lowercased()
        
        // Special cases first
        if lower == "thinking" {
            return UIImage(systemName: "brain")
        } else if lower.contains("loaded") || lower.contains("complete") || lower.contains("verified") || lower.contains("found") || lower.contains("created") || lower.contains("updated") || lower.contains("deleted") || lower.contains("saved") || lower.contains("recalled") || lower.contains("activated") {
            return UIImage(systemName: "checkmark.circle.fill")
        } else if lower.contains("template") {
            return UIImage(systemName: "doc.text")
        } else if lower.contains("exercise") {
            return UIImage(systemName: "figure.strengthtraining.traditional")
        } else if lower.contains("workout") {
            return UIImage(systemName: "figure.run")
        } else if lower.contains("routine") {
            return UIImage(systemName: "calendar")
        } else if lower.contains("profile") || lower.contains("user") {
            return UIImage(systemName: "person.circle")
        } else if lower.contains("search") || lower.contains("loading") || lower.contains("fetching") || lower.contains("checking") || lower.contains("browsing") || lower.contains("getting") {
            return UIImage(systemName: "magnifyingglass")
        } else if lower.contains("store") || lower.contains("memory") || lower.contains("saving") {
            return UIImage(systemName: "brain")
        } else {
            return UIImage(systemName: "gearshape")
        }
    }
    
    func setCompleted() {
        activityIndicator.stopAnimating()
        iconView.tintColor = .systemGreen
    }
    
    // MARK: - Reuse
    override func prepareForReuse() {
        super.prepareForReuse()
        activityLabel.text = nil
        iconView.image = nil
        iconView.tintColor = .secondaryLabel
        activityIndicator.stopAnimating()
    }
} 