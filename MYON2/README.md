# MYON2

An iOS fitness app built with Swift and Firebase.

## Setup Instructions

### Firebase Configuration

This project uses Firebase for authentication and data storage. To set up Firebase:

1. Go to the [Firebase Console](https://console.firebase.google.com/)
2. Create a new project or select your existing project
3. Add an iOS app to your project
4. Download the `GoogleService-Info.plist` file
5. Place it in the `MYON2/` directory (same level as `MYON2App.swift`)

**Important:** The `GoogleService-Info.plist` file contains sensitive API keys and should never be committed to version control. It's already added to `.gitignore` to prevent accidental commits.

### Project Structure

```
MYON2/
├── MYON2/
│   ├── GoogleService-Info.plist  # ← Add your Firebase config here (DO NOT COMMIT)
│   ├── MYON2App.swift
│   ├── Models/
│   ├── Views/
│   ├── Services/
│   └── ...
├── .gitignore
└── README.md
```

### Building the Project

1. Ensure you have Xcode installed
2. Place your `GoogleService-Info.plist` in the `MYON2/` directory
3. Open `MYON2.xcodeproj` in Xcode
4. Build and run the project

## Security Notes

- Never commit `GoogleService-Info.plist` to version control
- Keep your Firebase API keys secure
- Use environment-specific configurations for different build targets 