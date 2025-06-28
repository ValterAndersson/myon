# StrengthOS Firebase Functions Integration

This directory contains Firebase Cloud Functions that act as a proxy between the MYON iOS app and the StrengthOS agent deployed on Vertex AI Agent Engine.

## Architecture Overview

```
MYON iOS App 
    ↓ (Firebase Auth)
Firebase Functions (v2)
    ↓ (Google Cloud Auth)
Vertex AI Agent Engine
    ↓
StrengthOS ADK Agent
```

## Functions

All functions are Firebase v2 callable functions that require Firebase Authentication:

### 1. `createStrengthOSSession`
- Creates a new chat session for the authenticated user
- Returns a session ID that can be used for subsequent queries
- Sessions are managed client-side (no server persistence needed for ADK agents)

### 2. `listStrengthOSSessions`
- Lists all active sessions for the authenticated user
- Attempts to call the ADK agent's `list_sessions` method
- Returns empty array if sessions aren't supported by the agent

### 3. `queryStrengthOS`
- Sends a message to the StrengthOS agent
- Requires a message and optional session ID
- Uses the ADK agent's `query` class method
- Returns the agent's response

### 4. `deleteStrengthOSSession`
- Marks a session for deletion
- Currently returns success for client-side cleanup
- Sessions are managed by Agent Engine infrastructure

## Authentication Flow

1. **Client → Firebase Functions**: Uses Firebase Authentication (ID tokens)
2. **Firebase Functions → Vertex AI**: Uses Google Cloud Application Default Credentials
   - Service Account: `firebase-adminsdk-fbsvc@myon-53d85.iam.gserviceaccount.com`
   - Required Role: `roles/aiplatform.admin`

## Configuration

The Vertex AI configuration is stored in `config.js`:

```javascript
const VERTEX_AI_CONFIG = {
    projectId: '919326069447',
    location: 'us-central1',
    agentId: '4683295011721183232',
    projectName: 'myon-53d85'
};
```

## Deployment

These functions are automatically deployed when you run:

```bash
firebase deploy --only functions
```

## Testing

### From iOS App (Swift)

```swift
import FirebaseFunctions

let functions = Functions.functions(region: "us-central1")

// Create session
functions.httpsCallable("createStrengthOSSession").call() { result, error in
    if let error = error {
        print("Error: \(error)")
        return
    }
    
    if let data = result?.data as? [String: Any],
       let sessionId = data["sessionId"] as? String {
        print("Session created: \(sessionId)")
        
        // Query the agent
        let queryData = [
            "message": "Help me create a workout plan",
            "sessionId": sessionId
        ]
        
        functions.httpsCallable("queryStrengthOS").call(queryData) { result, error in
            if let data = result?.data as? [String: Any],
               let response = data["response"] as? String {
                print("Agent response: \(response)")
            }
        }
    }
}
```

### Local Testing with Firebase Emulator

```bash
# Start the emulators
firebase emulators:start --only functions

# Functions will be available at:
# http://localhost:5001/myon-53d85/us-central1/[function-name]
```

## Error Handling

All functions return standard Firebase error codes:
- `unauthenticated`: User is not authenticated
- `invalid-argument`: Missing required parameters
- `internal`: Server-side errors (check logs)

## Monitoring

View function logs in the Firebase Console or using:

```bash
firebase functions:log
```

## Important Notes

1. **V1/V2 Compatibility**: Functions support both Firebase Functions v1 and v2 request formats
2. **ADK Agent Pattern**: Uses `class_method` pattern specific to ADK agents
3. **Session Management**: Sessions are generated client-side; Agent Engine handles persistence
4. **Response Parsing**: Functions handle multiple response formats from the ADK agent 