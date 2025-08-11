import UIKit
import Combine

class ChatViewController: UIViewController {
    // MARK: - Properties
    var session: ChatSession?
    var isEmbedded = false // Flag to know if embedded in tab navigation
    
    private var collectionView: UICollectionView!
    private var messageComposer: MessageComposerView!
    private var placeholderView: UIView!
    private var messages: [ChatMessage] = []
    private var cancellables = Set<AnyCancellable>()
    private let chatService = ChatService.shared
    private var streamTask: Task<Void, Never>?
    
    // MARK: - Lifecycle
    override func viewDidLoad() {
        super.viewDidLoad()
        setupUI()
        setupNavigationBar()
        setupKeyboardHandling()
        loadSessionMessages()
    }
    
    override func viewWillDisappear(_ animated: Bool) {
        super.viewWillDisappear(animated)
        streamTask?.cancel()
    }
    
    // MARK: - UI Setup
    private func setupUI() {
        view.backgroundColor = .systemBackground
        
        // Setup collection view for messages
        let layout = createLayout()
        collectionView = UICollectionView(frame: .zero, collectionViewLayout: layout)
        collectionView.translatesAutoresizingMaskIntoConstraints = false
        collectionView.backgroundColor = .systemBackground
        collectionView.delegate = self
        collectionView.dataSource = self
        collectionView.keyboardDismissMode = .interactive
        
        // Register cell types
        collectionView.register(ChatMessageCell.self, forCellWithReuseIdentifier: "ChatMessageCell")
        collectionView.register(AgentActivityCell.self, forCellWithReuseIdentifier: "AgentActivityCell")
        
        // Setup message composer
        messageComposer = MessageComposerView()
        messageComposer.translatesAutoresizingMaskIntoConstraints = false
        messageComposer.delegate = self
        
        // Setup placeholder view
        setupPlaceholderView()
        
        // Add to view
        view.addSubview(collectionView)
        view.addSubview(placeholderView)
        view.addSubview(messageComposer)
        
        // Constraints
        NSLayoutConstraint.activate([
            collectionView.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor),
            collectionView.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            collectionView.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            collectionView.bottomAnchor.constraint(equalTo: messageComposer.topAnchor),
            
            placeholderView.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor),
            placeholderView.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            placeholderView.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            placeholderView.bottomAnchor.constraint(equalTo: messageComposer.topAnchor),
            
            messageComposer.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            messageComposer.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            messageComposer.bottomAnchor.constraint(equalTo: view.keyboardLayoutGuide.topAnchor)
        ])
        
        // Initially show placeholder if no messages
        updatePlaceholderVisibility()
    }
    
    private func setupNavigationBar() {
        // Only show navigation items if presented modally
        if !isEmbedded {
            title = "AI Coach"
            
            // Close button
            navigationItem.leftBarButtonItem = UIBarButtonItem(
                image: UIImage(systemName: "xmark"),
                style: .plain,
                target: self,
                action: #selector(closeTapped)
            )
        }
    }
    
    private func createLayout() -> UICollectionViewLayout {
        let itemSize = NSCollectionLayoutSize(
            widthDimension: .fractionalWidth(1.0),
            heightDimension: .estimated(100)
        )
        let item = NSCollectionLayoutItem(layoutSize: itemSize)
        
        let groupSize = NSCollectionLayoutSize(
            widthDimension: .fractionalWidth(1.0),
            heightDimension: .estimated(100)
        )
        let group = NSCollectionLayoutGroup.vertical(layoutSize: groupSize, subitems: [item])
        
        let section = NSCollectionLayoutSection(group: group)
        section.interGroupSpacing = 12
        // Use generous horizontal insets for document-like left-aligned assistant messages
        section.contentInsets = NSDirectionalEdgeInsets(top: 16, leading: 20, bottom: 16, trailing: 20)
        
        return UICollectionViewCompositionalLayout(section: section)
    }
    
    private func setupKeyboardHandling() {
        // Keyboard will show/hide is handled by keyboardLayoutGuide
    }
    
    func loadSessionMessages() {
        // Load historical messages from session
        guard let session = session else { return }
        
        title = session.title
        
        // Clear any existing messages first
        messages.removeAll()
        
        // Show loading indicator
        let loadingMessage = ChatMessage(
            content: .activity("Loading conversation history"),
            author: .system,
            timestamp: Date(),
            status: .sent
        )
        messages = [loadingMessage]
        collectionView.reloadData()
        
        // Load messages asynchronously
        Task {
            do {
                let historicalMessages = try await chatService.loadSessionMessages(for: session.id)
                
                // Update UI on main thread
                await MainActor.run {
                    // Replace loading message with actual messages
                    messages = historicalMessages
                    collectionView.reloadData()
                    updatePlaceholderVisibility()
                    
                    // Scroll to bottom if there are messages
                    if !messages.isEmpty {
                        scrollToBottom()
                    }
                }
            } catch {
                print("Failed to load session messages: \(error)")
                
                // Remove loading message on error
                await MainActor.run {
                    messages = []
                    collectionView.reloadData()
                    updatePlaceholderVisibility()
                }
            }
        }
    }
    
    // MARK: - Actions
    @objc private func closeTapped() {
        dismiss(animated: true)
    }
    
    // MARK: - Message Handling
    private func sendMessage(text: String, image: UIImage?) {
        guard var session = session else { return }
        
        // Create user message
        let userMessage = ChatMessage(
            content: image != nil ? .image(image!.jpegData(compressionQuality: 0.8)!, caption: text.isEmpty ? nil : text) : .text(text),
            author: .user,
            timestamp: Date(),
            status: .sent
        )
        
        // Add user message immediately
        messages.append(userMessage)
        let userIndexPath = IndexPath(item: messages.count - 1, section: 0)
        collectionView.performBatchUpdates({
            collectionView.insertItems(at: [userIndexPath])
        }, completion: { _ in
            self.scrollToBottom()
            self.updatePlaceholderVisibility()
        })
        
        // Convert image to data if present
        let imageData = image?.jpegData(compressionQuality: 0.8)
        
        // Cancel any existing stream
        streamTask?.cancel()
        
        // Start streaming
        streamTask = Task { @MainActor in
            do {
                let stream = chatService.streamMessage(
                    text,
                    sessionId: session.id,
                    imageData: imageData
                )
                
                for try await (message, sessionId) in stream {
                    // Update session ID if ADK returned a new one (for new conversations)
                    if let newSessionId = sessionId, session.id.hasPrefix("temp-") {
                        // Create a new session with the updated ID
                        let updatedSession = ChatSession(
                            id: newSessionId,
                            userId: session.userId,
                            title: session.title,
                            lastMessage: session.lastMessage,
                            lastUpdated: session.lastUpdated,
                            messageCount: session.messageCount,
                            isActive: session.isActive
                        )
                        session = updatedSession
                        self.session = updatedSession
                        
                        // Notify parent view about the updated session
                        NotificationCenter.default.post(
                            name: Notification.Name("SessionUpdated"),
                            object: nil,
                            userInfo: ["session": updatedSession]
                        )
                    }
                    
                    // Handle special REMOVE_THINKING messages
                    if case .activity(let text) = message.content, text == "REMOVE_THINKING" {
                        // Find and remove the last "Thinking" message
                        for i in (0..<messages.count).reversed() {
                            if case .activity(let activity) = messages[i].content, activity == "Thinking" {
                                messages.remove(at: i)
                                let indexPath = IndexPath(item: i, section: 0)
                                collectionView.performBatchUpdates({
                                    collectionView.deleteItems(at: [indexPath])
                                }, completion: nil)
                                break
                            }
                        }
                        continue // Don't add the REMOVE_THINKING message itself
                    }
                    
                    // Check if this is a text message that should replace a typing indicator
                    var shouldInsert = true
                    if case .text(let text) = message.content,
                       message.author == .agent,
                       text != "…" {
                        // Look for typing indicator to replace
                        for i in (0..<messages.count).reversed() {
                            if case .text("…") = messages[i].content,
                               messages[i].author == .agent,
                               messages[i].status == .streaming {
                                // Replace typing indicator with actual message
                                messages[i] = message
                                shouldInsert = false
                                
                                // Update the cell
                                let indexPath = IndexPath(item: i, section: 0)
                                collectionView.performBatchUpdates({
                                    collectionView.reloadItems(at: [indexPath])
                                }, completion: { _ in
                                    self.scrollToBottom()
                                })
                                break
                            }
                        }
                    }
                    
                    if shouldInsert {
                        // Always append new message chunks to create streaming effect
                        messages.append(message)
                        
                        // Insert new cell using batch updates for safety
                        let indexPath = IndexPath(item: messages.count - 1, section: 0)
                        collectionView.performBatchUpdates({
                            collectionView.insertItems(at: [indexPath])
                        }, completion: { _ in
                            self.scrollToBottom()
                            self.updatePlaceholderVisibility()
                        })
                    }
                }
            } catch {
                print("Stream error: \(error)")
                showError(error)
            }
        }
    }
    
    private func scrollToBottom() {
        guard !messages.isEmpty else { return }
        let lastIndex = IndexPath(item: messages.count - 1, section: 0)
        collectionView.scrollToItem(at: lastIndex, at: .bottom, animated: true)
    }
    
    private func showError(_ error: Error) {
        let alert = UIAlertController(
            title: "Error",
            message: error.localizedDescription,
            preferredStyle: .alert
        )
        alert.addAction(UIAlertAction(title: "OK", style: .default))
        present(alert, animated: true)
    }
    
    private func setupPlaceholderView() {
        placeholderView = UIView()
        placeholderView.translatesAutoresizingMaskIntoConstraints = false
        placeholderView.backgroundColor = .systemBackground
        
        // Container stack view
        let stackView = UIStackView()
        stackView.axis = .vertical
        stackView.alignment = .center
        stackView.spacing = 24
        stackView.translatesAutoresizingMaskIntoConstraints = false
        
        // Brain icon
        let iconImageView = UIImageView()
        iconImageView.image = UIImage(systemName: "brain")
        iconImageView.tintColor = .systemBlue
        iconImageView.contentMode = .scaleAspectFit
        iconImageView.translatesAutoresizingMaskIntoConstraints = false
        
        // Title label
        let titleLabel = UILabel()
        titleLabel.text = "Ready to Transform Your Training"
        titleLabel.font = .systemFont(ofSize: 24, weight: .bold)
        titleLabel.textAlignment = .center
        titleLabel.numberOfLines = 0
        
        // Description label
        let descriptionLabel = UILabel()
        descriptionLabel.text = "StrengthOS has full access to your workouts, templates, and routines. I can analyze your training history, create personalized programs, and help you optimize every session.\n\nStart your journey to smarter, more effective training today."
        descriptionLabel.font = .systemFont(ofSize: 16)
        descriptionLabel.textColor = .secondaryLabel
        descriptionLabel.textAlignment = .center
        descriptionLabel.numberOfLines = 0
        
        // Add to stack view
        stackView.addArrangedSubview(iconImageView)
        stackView.addArrangedSubview(titleLabel)
        stackView.addArrangedSubview(descriptionLabel)
        
        placeholderView.addSubview(stackView)
        
        // Constraints
        NSLayoutConstraint.activate([
            iconImageView.widthAnchor.constraint(equalToConstant: 80),
            iconImageView.heightAnchor.constraint(equalToConstant: 80),
            
            stackView.centerYAnchor.constraint(equalTo: placeholderView.centerYAnchor, constant: -40),
            stackView.leadingAnchor.constraint(equalTo: placeholderView.leadingAnchor, constant: 40),
            stackView.trailingAnchor.constraint(equalTo: placeholderView.trailingAnchor, constant: -40),
            
            titleLabel.leadingAnchor.constraint(equalTo: stackView.leadingAnchor),
            titleLabel.trailingAnchor.constraint(equalTo: stackView.trailingAnchor),
            
            descriptionLabel.leadingAnchor.constraint(equalTo: stackView.leadingAnchor),
            descriptionLabel.trailingAnchor.constraint(equalTo: stackView.trailingAnchor)
        ])
    }
    
    private func updatePlaceholderVisibility() {
        let hasRealMessages = messages.contains { message in
            // Don't count loading messages as real messages
            if case .activity(let text) = message.content {
                return text != "Loading conversation history"
            }
            return true
        }
        
        placeholderView.isHidden = hasRealMessages
        collectionView.isHidden = !hasRealMessages
    }
}

// MARK: - UICollectionView DataSource
extension ChatViewController: UICollectionViewDataSource {
    func collectionView(_ collectionView: UICollectionView, numberOfItemsInSection section: Int) -> Int {
        return messages.count
    }
    
    func collectionView(_ collectionView: UICollectionView, cellForItemAt indexPath: IndexPath) -> UICollectionViewCell {
        let message = messages[indexPath.item]
        
        switch message.content {
        case .activity(let text):
            let cell = collectionView.dequeueReusableCell(withReuseIdentifier: "AgentActivityCell", for: indexPath) as! AgentActivityCell
            cell.configure(with: text)
            return cell
        case .functionCall(let name, _):
            let cell = collectionView.dequeueReusableCell(withReuseIdentifier: "AgentActivityCell", for: indexPath) as! AgentActivityCell
            cell.configure(with: "Calling " + name + "…")
            return cell
        default:
            let cell = collectionView.dequeueReusableCell(withReuseIdentifier: "ChatMessageCell", for: indexPath) as! ChatMessageCell
            cell.configure(with: message)
            return cell
        }
    }
}

// MARK: - UICollectionView Delegate
extension ChatViewController: UICollectionViewDelegate {
    // Handle selection if needed
}

// MARK: - MessageComposerDelegate
extension ChatViewController: MessageComposerDelegate {
    func messageComposer(_ composer: MessageComposerView, didSendMessage text: String, image: UIImage?) {
        sendMessage(text: text, image: image)
    }
    
    func messageComposerDidTapCamera(_ composer: MessageComposerView) {
        // Check camera permissions
        let imagePickerController = UIImagePickerController()
        imagePickerController.delegate = self
        imagePickerController.sourceType = .camera
        imagePickerController.allowsEditing = false
        present(imagePickerController, animated: true)
    }
    
    func messageComposerDidTapGallery(_ composer: MessageComposerView) {
        let imagePickerController = UIImagePickerController()
        imagePickerController.delegate = self
        imagePickerController.sourceType = .photoLibrary
        imagePickerController.allowsEditing = false
        present(imagePickerController, animated: true)
    }
}

// MARK: - UIImagePickerControllerDelegate
extension ChatViewController: UIImagePickerControllerDelegate, UINavigationControllerDelegate {
    func imagePickerController(_ picker: UIImagePickerController, didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey : Any]) {
        if let image = info[.originalImage] as? UIImage {
            messageComposer.showImagePreview(image)
        }
        picker.dismiss(animated: true)
    }
    
    func imagePickerControllerDidCancel(_ picker: UIImagePickerController) {
        picker.dismiss(animated: true)
    }
} 