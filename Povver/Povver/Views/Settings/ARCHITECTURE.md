# Settings Views Architecture

> Module-level architecture for the Settings views under `Views/Settings/`.

## Purpose

Settings and account management UI accessed from the More tab hub (`MoreView`). Covers profile editing, preferences, security operations, activity/recommendations, and subscription management.

## File Structure

| File | Type | Presentation | Purpose |
|------|------|-------------|---------|
| `ActivityView.swift` | Push | NavigationLink from MoreView | Recommendations feed with auto-pilot toggle |
| `ProfileEditView.swift` | Push | NavigationLink from MoreView profile card | Account info + body metrics editing |
| `PreferencesView.swift` | Push | NavigationLink from MoreView | Timezone, week start preferences |
| `SecurityView.swift` | Push | NavigationLink from MoreView | Links to auth management views |
| `SubscriptionView.swift` | Push | NavigationLink from MoreView | Subscription status & management |
| `ReauthenticationView.swift` | Sheet (half) | `.presentationDetents([.medium])` | Multi-provider reauthentication before sensitive operations |
| `EmailChangeView.swift` | Sheet (half) | `.presentationDetents([.medium])` | Email change with verification link |
| `PasswordChangeView.swift` | Sheet (half) | `.presentationDetents([.medium])` | Change password (email users) or set password (SSO-only users) |
| `ForgotPasswordView.swift` | Sheet (full) | `.presentationDetents([.large])` | Forgot password flow from login screen |
| `LinkedAccountsView.swift` | Push | NavigationLink from SecurityView | Link/unlink auth providers |
| `DeleteAccountView.swift` | Push | NavigationLink from SecurityView | Account deletion with reauth + confirmation |

## Entry Points

All views are accessed from `MoreView.swift` (the More tab hub), except:
- `ForgotPasswordView` — presented from `LoginView.swift` ("Forgot Password?" link)
- `ReauthenticationView` — presented by `EmailChangeView` and `DeleteAccountView` when reauthentication is needed
- `LinkedAccountsView`, `DeleteAccountView` — pushed from `SecurityView`
- `PasswordChangeView` — presented as sheet from `SecurityView` or `ProfileEditView`
- `EmailChangeView` — presented as sheet from `ProfileEditView`

## Data Flow

```
MoreView (Views/Tabs/MoreView.swift)
    │
    ├─ Profile card → ProfileEditView
    │   ├─ Account: Nickname, Email (edit sheets)
    │   ├─ Body Metrics: Height, Weight, Fitness Level (edit sheets)
    │   └─ Email/Password change sheets
    │
    ├─ Activity → ActivityView
    │   ├─ Auto-pilot toggle → UserRepository.updateAutoPilot()
    │   └─ Recommendation cards → RecommendationsViewModel.accept() / reject()
    │
    ├─ Preferences → PreferencesView
    │   └─ Week start toggle → UserRepository.updateUserProfile()
    │
    ├─ Security → SecurityView
    │   ├─ NavigationLink → LinkedAccountsView
    │   │   └─ authService.linkGoogle() / linkApple() / unlinkProvider()
    │   │
    │   ├─ Button → PasswordChangeView (sheet)
    │   │   └─ authService.changePassword() / setPassword()
    │   │
    │   └─ NavigationLink → DeleteAccountView
    │       └─ ReauthenticationView (sheet) → authService.deleteAccount()
    │
    ├─ Subscription → SubscriptionView
    │
LoginView
    └─ Button → ForgotPasswordView (sheet)
        └─ authService.sendPasswordReset()
```

## Patterns

### State Machine Views

Several views use a state machine pattern with distinct UI states:

- **ForgotPasswordView**: `formState` → `sentState` (with "try again" link to go back)
- **EmailChangeView**: `ssoDisabledState` | `changeEmailForm` → `verificationSentState`
- **PasswordChangeView**: `passwordForm` → `successState`
- **DeleteAccountView**: warning screen → reauth sheet → confirmation dialog → deletion

### Auto-Pilot Toggle (ActivityView)

ActivityView loads `autoPilotEnabled` from Firestore in `.task` (not passed as a parameter) to avoid stale state. The toggle uses optimistic update with rollback on Firestore failure, guarded by `isTogglingAutoPilot` to prevent rapid-toggle race conditions:

1. Guard: if a write is already in-flight, ignore the toggle
2. Toggle switches immediately (optimistic), `isTogglingAutoPilot = true`
3. Firestore write fires in background
4. On failure: toggle reverts to previous value, error banner shown
5. On success: analytics event logged
6. `isTogglingAutoPilot = false` — toggle re-enabled

### Recommendation Card Modes

RecommendationCardView accepts `autoPilotEnabled: Bool` to control visual treatment:
- `pending_review` → interactive (Accept/Decline buttons), regardless of auto-pilot
- `applied` by agent + auto-pilot ON → notice with emerald accent bar, muted changes
- `applied` by user → notice with "Applied" status
- `acknowledged` → notice with "Noted" status

### Reauthentication Trigger

`EmailChangeView` and `DeleteAccountView` handle the `requiresRecentLogin` error from Firebase:

```swift
let nsError = error as NSError
if AuthErrorCode(rawValue: nsError.code) == .requiresRecentLogin {
    showingReauth = true
}
```

### Provider-Conditional UI

Several views adapt based on linked providers:

- **EmailChangeView**: SSO-only users see a disabled state; email users see the change form
- **PasswordChangeView**: title is "Change Password" vs "Set Password"
- **LinkedAccountsView**: unlink button hidden when only 1 provider remains
- **ProfileEditView**: email row hidden for SSO-only users; Apple relay emails hidden
- **SecurityView**: password row label adapts based on linked providers

### Error Display

All views surface errors via `@State private var errorMessage: String?` displayed as inline banners:

- **Auth views** (EmailChangeView, PasswordChangeView, etc.): use `AuthService.friendlyAuthError(error)` for Firebase auth errors
- **Settings views** (ProfileEditView, PreferencesView, MoreView): use plain error strings for save/load failures
- **ActivityView**: uses both local `errorMessage` (auto-pilot toggle failures) and `viewModel.errorMessage` (recommendation accept/reject failures)

```swift
@State private var errorMessage: String?

} catch {
    errorMessage = "Failed to save. Please try again."
}

if let errorMessage = errorMessage {
    Text(errorMessage)
        .textStyle(.caption)
        .foregroundColor(.destructive)
}
```

## Dependencies

| Dependency | Used By | Purpose |
|------------|---------|---------|
| `AuthService.shared` | SecurityView, ProfileEditView, PreferencesView, auth views | Auth operations |
| `RecommendationsViewModel` | ActivityView | Recommendation state + accept/reject |
| `UserRepository.shared` | ProfileEditView, PreferencesView, ActivityView | Firestore user data |
| `WorkoutRepository` | ProfileEditView | Session count via `getWorkoutCount()` aggregation |
| `SubscriptionService.shared` | SubscriptionView | Subscription state |
| `SheetScaffold` | ProfileEditView, EmailChangeView, PasswordChangeView | Consistent sheet chrome |
| `PovverButton` | All views | Styled buttons |
| `ProfileRow`, `ProfileRowToggle`, `ProfileRowLinkContent` | All settings views | Navigation row styling |
| `BadgeView` | MoreView (via ProfileRowLinkContent) | Badge on Activity row |
