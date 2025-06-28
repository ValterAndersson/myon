import UIKit

protocol MessageComposerDelegate: AnyObject {
    func messageComposer(_ composer: MessageComposerView, didSendMessage text: String, image: UIImage?)
    func messageComposerDidTapCamera(_ composer: MessageComposerView)
    func messageComposerDidTapGallery(_ composer: MessageComposerView)
}

class MessageComposerView: UIView {
    // MARK: - Properties
    weak var delegate: MessageComposerDelegate?
    
    private let containerStack = UIStackView()
    private let imagePreviewContainer = UIView()
    private let inputContainer = UIView()
    
    // Image preview components
    private let imagePreview = UIImageView()
    private let removeImageButton = UIButton(type: .custom)
    private var selectedImage: UIImage?
    
    // Input components
    private let textView = UITextView()
    private let placeholderLabel = UILabel()
    private let cameraButton = UIButton(type: .system)
    private let galleryButton = UIButton(type: .system)
    private let sendButton = UIButton(type: .system)
    private let buttonStack = UIStackView()
    
    // Constraints
    private var textViewHeightConstraint: NSLayoutConstraint!
    private var imagePreviewHeightConstraint: NSLayoutConstraint!
    
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
        backgroundColor = .systemBackground
        
        // Container setup
        containerStack.axis = .vertical
        containerStack.spacing = 8
        containerStack.translatesAutoresizingMaskIntoConstraints = false
        
        // Image preview setup
        setupImagePreview()
        
        // Input container setup
        setupInputContainer()
        
        // Add separator
        let separator = UIView()
        separator.backgroundColor = .separator
        separator.translatesAutoresizingMaskIntoConstraints = false
        
        addSubview(separator)
        addSubview(containerStack)
        
        containerStack.addArrangedSubview(imagePreviewContainer)
        containerStack.addArrangedSubview(inputContainer)
        
        // Constraints
        NSLayoutConstraint.activate([
            separator.topAnchor.constraint(equalTo: topAnchor),
            separator.leadingAnchor.constraint(equalTo: leadingAnchor),
            separator.trailingAnchor.constraint(equalTo: trailingAnchor),
            separator.heightAnchor.constraint(equalToConstant: 0.5),
            
            containerStack.topAnchor.constraint(equalTo: separator.bottomAnchor, constant: 8),
            containerStack.leadingAnchor.constraint(equalTo: leadingAnchor, constant: 16),
            containerStack.trailingAnchor.constraint(equalTo: trailingAnchor, constant: -16),
            containerStack.bottomAnchor.constraint(equalTo: safeAreaLayoutGuide.bottomAnchor, constant: -8)
        ])
        
        // Initially hide image preview
        imagePreviewContainer.isHidden = true
    }
    
    private func setupImagePreview() {
        imagePreviewContainer.translatesAutoresizingMaskIntoConstraints = false
        
        // Image view
        imagePreview.contentMode = .scaleAspectFill
        imagePreview.clipsToBounds = true
        imagePreview.layer.cornerRadius = 8
        imagePreview.translatesAutoresizingMaskIntoConstraints = false
        
        // Remove button
        removeImageButton.setImage(UIImage(systemName: "xmark.circle.fill"), for: .normal)
        removeImageButton.tintColor = .white
        removeImageButton.backgroundColor = UIColor.black.withAlphaComponent(0.6)
        removeImageButton.layer.cornerRadius = 12
        removeImageButton.translatesAutoresizingMaskIntoConstraints = false
        removeImageButton.addTarget(self, action: #selector(removeImageTapped), for: .touchUpInside)
        
        imagePreviewContainer.addSubview(imagePreview)
        imagePreviewContainer.addSubview(removeImageButton)
        
        imagePreviewHeightConstraint = imagePreviewContainer.heightAnchor.constraint(equalToConstant: 80)
        
        NSLayoutConstraint.activate([
            imagePreviewHeightConstraint,
            
            imagePreview.leadingAnchor.constraint(equalTo: imagePreviewContainer.leadingAnchor),
            imagePreview.topAnchor.constraint(equalTo: imagePreviewContainer.topAnchor),
            imagePreview.bottomAnchor.constraint(equalTo: imagePreviewContainer.bottomAnchor),
            imagePreview.widthAnchor.constraint(equalToConstant: 80),
            
            removeImageButton.topAnchor.constraint(equalTo: imagePreview.topAnchor, constant: -8),
            removeImageButton.trailingAnchor.constraint(equalTo: imagePreview.trailingAnchor, constant: 8),
            removeImageButton.widthAnchor.constraint(equalToConstant: 24),
            removeImageButton.heightAnchor.constraint(equalToConstant: 24)
        ])
    }
    
    private func setupInputContainer() {
        inputContainer.translatesAutoresizingMaskIntoConstraints = false
        
        // Text view setup
        textView.font = .systemFont(ofSize: 17)
        textView.textColor = .label
        textView.backgroundColor = .secondarySystemBackground
        textView.layer.cornerRadius = 20
        textView.textContainerInset = UIEdgeInsets(top: 12, left: 16, bottom: 12, right: 16)
        textView.isScrollEnabled = false
        textView.delegate = self
        textView.translatesAutoresizingMaskIntoConstraints = false
        
        // Placeholder
        placeholderLabel.text = "Message"
        placeholderLabel.font = .systemFont(ofSize: 17)
        placeholderLabel.textColor = .placeholderText
        placeholderLabel.translatesAutoresizingMaskIntoConstraints = false
        
        // Buttons
        cameraButton.setImage(UIImage(systemName: "camera.fill"), for: .normal)
        cameraButton.tintColor = .systemBlue
        cameraButton.addTarget(self, action: #selector(cameraTapped), for: .touchUpInside)
        
        galleryButton.setImage(UIImage(systemName: "photo.fill"), for: .normal)
        galleryButton.tintColor = .systemBlue
        galleryButton.addTarget(self, action: #selector(galleryTapped), for: .touchUpInside)
        
        sendButton.setImage(UIImage(systemName: "arrow.up.circle.fill"), for: .normal)
        sendButton.tintColor = .systemBlue
        sendButton.addTarget(self, action: #selector(sendTapped), for: .touchUpInside)
        sendButton.isEnabled = false
        
        // Button stack
        buttonStack.axis = .horizontal
        buttonStack.spacing = 12
        buttonStack.alignment = .center
        buttonStack.translatesAutoresizingMaskIntoConstraints = false
        
        buttonStack.addArrangedSubview(cameraButton)
        buttonStack.addArrangedSubview(galleryButton)
        buttonStack.addArrangedSubview(sendButton)
        
        // Add to container
        inputContainer.addSubview(textView)
        inputContainer.addSubview(placeholderLabel)
        inputContainer.addSubview(buttonStack)
        
        textViewHeightConstraint = textView.heightAnchor.constraint(greaterThanOrEqualToConstant: 44)
        
        NSLayoutConstraint.activate([
            textView.leadingAnchor.constraint(equalTo: inputContainer.leadingAnchor),
            textView.topAnchor.constraint(equalTo: inputContainer.topAnchor),
            textView.bottomAnchor.constraint(equalTo: inputContainer.bottomAnchor),
            textViewHeightConstraint,
            
            placeholderLabel.leadingAnchor.constraint(equalTo: textView.leadingAnchor, constant: 20),
            placeholderLabel.centerYAnchor.constraint(equalTo: textView.centerYAnchor),
            
            buttonStack.trailingAnchor.constraint(equalTo: inputContainer.trailingAnchor),
            buttonStack.centerYAnchor.constraint(equalTo: textView.centerYAnchor),
            buttonStack.leadingAnchor.constraint(equalTo: textView.trailingAnchor, constant: 8),
            
            cameraButton.widthAnchor.constraint(equalToConstant: 32),
            cameraButton.heightAnchor.constraint(equalToConstant: 32),
            galleryButton.widthAnchor.constraint(equalToConstant: 32),
            galleryButton.heightAnchor.constraint(equalToConstant: 32),
            sendButton.widthAnchor.constraint(equalToConstant: 32),
            sendButton.heightAnchor.constraint(equalToConstant: 32)
        ])
    }
    
    // MARK: - Actions
    @objc private func cameraTapped() {
        delegate?.messageComposerDidTapCamera(self)
    }
    
    @objc private func galleryTapped() {
        delegate?.messageComposerDidTapGallery(self)
    }
    
    @objc private func sendTapped() {
        guard let text = textView.text, !text.isEmpty else { return }
        delegate?.messageComposer(self, didSendMessage: text, image: selectedImage)
        
        // Clear
        textView.text = ""
        selectedImage = nil
        imagePreviewContainer.isHidden = true
        updateSendButton()
        textViewDidChange(textView)
    }
    
    @objc private func removeImageTapped() {
        selectedImage = nil
        UIView.animate(withDuration: 0.3) {
            self.imagePreviewContainer.isHidden = true
        }
        updateSendButton()
    }
    
    // MARK: - Public Methods
    func showImagePreview(_ image: UIImage) {
        selectedImage = image
        imagePreview.image = image
        
        UIView.animate(withDuration: 0.3) {
            self.imagePreviewContainer.isHidden = false
        }
        updateSendButton()
    }
    
    // MARK: - Private Methods
    private func updateSendButton() {
        let hasText = !(textView.text?.isEmpty ?? true)
        let hasImage = selectedImage != nil
        sendButton.isEnabled = hasText || hasImage
    }
}

// MARK: - UITextViewDelegate
extension MessageComposerView: UITextViewDelegate {
    func textViewDidChange(_ textView: UITextView) {
        // Update placeholder
        placeholderLabel.isHidden = !textView.text.isEmpty
        
        // Update send button
        updateSendButton()
        
        // Update height
        let size = textView.sizeThatFits(CGSize(width: textView.frame.width, height: CGFloat.infinity))
        let newHeight = max(44, min(size.height, 120))
        
        if textViewHeightConstraint.constant != newHeight {
            textViewHeightConstraint.constant = newHeight
            UIView.animate(withDuration: 0.2) {
                self.superview?.layoutIfNeeded()
            }
        }
        
        textView.isScrollEnabled = size.height > 120
    }
    
    func textViewDidBeginEditing(_ textView: UITextView) {
        // Could add animations here
    }
    
    func textViewDidEndEditing(_ textView: UITextView) {
        // Could add animations here
    }
} 