# Settings Views Architecture

> Module-level architecture for the Settings views under `Views/Settings/`.

## Purpose

Account management UI for authentication operations that require dedicated screens: reauthentication, email/password changes, provider linking, and account deletion. All views interact with `AuthService.shared` for auth operations and display errors via `AuthService.friendlyAuthError()`.

## File Structure

| File | Type | Presentation | Purpose |
|------|------|-------------|---------|
| `ReauthenticationView.swift` | Sheet (half) | `.presentationDetents([.medium])` | Multi-provider reauthentication before sensitive operations |
| `EmailChangeView.swift` | Sheet (half) | `.presentationDetents([.medium])` | Email change with verification link |
| `PasswordChangeView.swift` | Sheet (half) | `.presentationDetents([.medium])` | Change password (email users) or set password (SSO-only users) |
| `ForgotPasswordView.swift` | Sheet (full) | `.presentationDetents([.large])` | Forgot password flow from login screen |
| `LinkedAccountsView.swift` | Push | NavigationLink from ProfileView | Link/unlink auth providers |
| `DeleteAccountView.swift` | Push | NavigationLink from ProfileView | Account deletion with reauth + confirmation |

## Entry Points

All views are accessed from `ProfileView.swift` (Security section), except:
- `ForgotPasswordView` — presented from `LoginView.swift` ("Forgot Password?" link)
- `ReauthenticationView` — presented by `EmailChangeView` and `DeleteAccountView` when reauthentication is needed

## Patterns

### State Machine Views

Several views use a state machine pattern with distinct UI states:

- **ForgotPasswordView**: `formState` → `sentState` (with "try again" link to go back)
- **EmailChangeView**: `ssoDisabledState` | `changeEmailForm` → `verificationSentState`
- **PasswordChangeView**: `passwordForm` → `successState`
- **DeleteAccountView**: warning screen → reauth sheet → confirmation dialog → deletion

### Reauthentication Trigger

`EmailChangeView` and `DeleteAccountView` handle the `requiresRecentLogin` error from Firebase:

```swift
let nsError = error as NSError
if AuthErrorCode(rawValue: nsError.code) == .requiresRecentLogin {
    showingReauth = true
}
```

`ReauthenticationView` receives the linked providers and shows verification options accordingly. On success, it calls `onSuccess()` and dismisses itself.

### Provider-Conditional UI

Several views adapt based on linked providers:

- **EmailChangeView**: SSO-only users see a disabled state with lock icon; email users see the change form
- **PasswordChangeView**: title is "Change Password" vs "Set Password"; current password field only shown for email users
- **LinkedAccountsView**: unlink button hidden when only 1 provider remains
- **ProfileView**: email row is tappable only if `.email` provider is linked; password row label adapts

### Error Display

All views follow the same error pattern:
```swift
@State private var errorMessage: String?

// In async action:
} catch {
    errorMessage = AuthService.friendlyAuthError(error)
}

// In view body:
if let errorMessage = errorMessage {
    Text(errorMessage)
        .textStyle(.caption)
        .foregroundColor(.destructive)
}
```

## Dependencies

| Dependency | Used By | Purpose |
|------------|---------|---------|
| `AuthService.shared` | All views | Auth operations |
| `SheetScaffold` | EmailChangeView, PasswordChangeView | Consistent sheet chrome |
| `PovverButton` | All views | Styled buttons |
| `ProfileRowLinkContent` | ProfileView (entry point) | Navigation row styling |
| `UserRepository.shared` | DeleteAccountView (via AuthService) | Firestore user data deletion |

## Data Flow

```
ProfileView
    │
    ├─ Security section
    │   ├─ NavigationLink → LinkedAccountsView
    │   │   └─ authService.linkGoogle() / linkApple() / unlinkProvider()
    │   │
    │   ├─ Button → PasswordChangeView (sheet)
    │   │   └─ authService.changePassword() / setPassword()
    │   │
    │   └─ NavigationLink → DeleteAccountView
    │       └─ ReauthenticationView (sheet) → authService.deleteAccount()
    │
    ├─ Account section
    │   └─ Button → EmailChangeView (sheet)
    │       └─ ReauthenticationView (sheet) → authService.changeEmail()
    │
LoginView
    └─ Button → ForgotPasswordView (sheet)
        └─ authService.sendPasswordReset()
```

## Troubleshooting

### "For your security, please sign in again to continue"
Firebase requires recent authentication for sensitive operations. The `requiresRecentLogin` error triggers `ReauthenticationView`. If this happens repeatedly, check that the reauthentication is actually completing (not just dismissing the sheet).

### Provider data not updating after link/unlink
`LinkedAccountsView` refreshes via `authService.reloadCurrentUser()` in `.task` and reads `authService.linkedProviders` in `.onAppear`. If providers appear stale, verify that `reloadCurrentUser()` calls `user.reload()` and reassigns `Auth.auth().currentUser`.

### "This account is already linked to a different Povver account"
This `credentialAlreadyInUse` error means the SSO account is linked to another Firebase Auth user. Firebase's "one account per email" may have auto-linked the provider during a previous sign-in. Check Firebase Auth console for the provider state.

### Apple Sign-In shows no email / wrong name
Apple only provides name and email on the **first** sign-in. Subsequent sign-ins return nil for these fields. The Firestore user document stores the initial values. If the user chose "Hide My Email", a private relay address is used — this won't match an existing email account for auto-linking.

### Account deletion fails silently
Check the deletion sequence: Apple token revocation (may silently fail with `try?`) → Firestore deletion → Auth deletion. If Firestore deletion fails, the Auth account persists. If Auth deletion fails with `requiresRecentLogin`, the reauth sheet is re-presented.
