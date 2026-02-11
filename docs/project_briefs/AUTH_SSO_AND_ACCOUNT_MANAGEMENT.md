# Project Brief: Google & Apple Sign-In + Account Management

## Objective

Add Google Sign-In, Apple Sign-In, and full account management (change email, change password, link/unlink providers, delete account) to the Povver iOS app. The Firebase Functions backend requires **zero changes** — the existing middleware uses `getAuth().verifyIdToken()` which validates any Firebase Auth token regardless of sign-in provider.

---

## Decisions Already Made

These were discussed and agreed upon. Do not re-deliberate.

1. **Account collision UX**: Show a friendly error message. No smart flow (no saving pending credentials, no auto-linking). The message directs users to sign in with their original method and link providers in settings.

2. **Provider linking**: Purely optional. Users can link/unlink in a settings screen. No prompting or nudging to link.

3. **Email field for SSO users**: Greyed out with helper text "Changing email is not possible when signed in with {provider}". Email/password users get a working change-email flow with verification.

4. **New account confirmation**: When SSO sign-in creates a new Firebase Auth user (`isNewUser == true`), show a confirmation dialog before creating the Firestore user document: "You are creating a new Povver account with {provider}. Continue?" Cancel cleans up the auto-created auth record.

5. **Data model**: Keep `provider: String` in Firestore as the original sign-up method. Use `Auth.auth().currentUser?.providerData` at runtime for linked providers. No need to sync Firestore with linked state.

6. **Delivery order**: Account management first (testable with email-only), then Google, then Apple — each as a separate commit.

7. **Error messages**: All Firebase auth errors surfaced to users must be friendly and actionable (see error table below). Never show raw Firebase error strings.

---

## Startup Checklist

Read these files before writing any code. They are listed in dependency order — later files reference concepts from earlier ones.

### 1. Architecture docs (understand the system)

| # | File | Why |
|---|------|-----|
| 1 | `docs/SYSTEM_ARCHITECTURE.md` | Cross-layer data flows, auth patterns, Firestore as source of truth |
| 2 | `docs/IOS_ARCHITECTURE.md` | MVVM structure, services layer, view organization |
| 3 | `docs/FIRESTORE_SCHEMA.md` | Users collection schema, all subcollections under `users/{uid}`, security rules |

### 2. Source files you will modify (understand current implementation)

| # | File | What to look for |
|---|------|-----------------|
| 4 | `Povver/Povver/Services/AuthService.swift` | 72 lines. Email sign-up/sign-in, stub methods for Google/Apple, signOut. User doc created client-side in `signUp()`. Note: writes `"email"` as provider value, not Firebase's `"password"` ID. |
| 5 | `Povver/Povver/Models/User.swift` | Codable struct: `provider: String`, `email: String`, `uid: String`, `name: String?`, `weekStartsOnMonday: Bool`, `timeZone: String?`. CodingKeys map snake_case. |
| 6 | `Povver/Povver/Repositories/UserRepository.swift` | `deleteUser()` at line 85 has a **broken subcollection list** — uses `"workout_templates"` (doesn't exist) and is missing most subcollections. Must be fixed. |
| 7 | `Povver/Povver/Views/LoginView.swift` | Email form + 2 SSO stub buttons. `performLogin()` calls `authService.signIn()` → `session.startSession(userId:)` → `onLogin?(userId)`. The `onLogin` callback triggers `flow = .main` in RootView. Error shown via `errorMessage` state. Has private `authTextField()` ViewBuilder. |
| 8 | `Povver/Povver/Views/RegisterView.swift` | Nearly identical to LoginView. `performRegistration()` calls `authService.signUp()` → `session.startSession(userId:)` → `onRegister?(userId)`. Same `authTextField()` helper. |
| 9 | `Povver/Povver/Views/Tabs/ProfileView.swift` | Settings screen. Sections: Profile Header, Account (email + nickname), Body Metrics, Preferences, More, Sign Out. Uses `ProfileRow`, `ProfileRowToggle`, `ProfileRowLinkContent` components. Edit sheets use `SheetScaffold`. Data loaded via async `loadProfile()` in `.task {}`. |
| 10 | `Povver/Povver/Views/RootView.swift` | `AppFlow` enum: `.login`, `.register`, `.main`. **Callback-driven** — not reactive to auth state. `LoginView(onLogin: { _ in flow = .main })`. SSO buttons must follow this same pattern. |
| 11 | `Povver/Povver/PovverApp.swift` | App entry point. 21 lines. Just `FirebaseConfig.shared.configure()` and `RootView()`. Needs `.onOpenURL` for Google Sign-In. |

### 3. UI patterns to follow (match existing design system)

| # | File | Key details |
|---|------|------------|
| 12 | `Povver/Povver/UI/Components/PovverButton.swift` | Styles: `.primary` (emerald), `.secondary` (bordered), `.ghost` (transparent), `.destructive` (red). Supports `leadingIcon: Image`. Full-width, 12pt corner radius. |
| 13 | `Povver/Povver/UI/Components/Sheets/SheetScaffold.swift` | Standard modal pattern: Cancel/Done nav bar, `.presentationDetents([.medium])`, `.presentationBackground(Color.surfaceElevated)`. All edit sheets in ProfileView use this. |
| 14 | `Povver/Povver/UI/DesignSystem/Tokens.swift` | Spacing: `Space.sm=8, .md=12, .lg=16, .xl=24, .xxl=32`. Colors: `.accent`, `.destructive`, `.surface`, `.bg`, `.textPrimary/Secondary/Tertiary`. Typography: `.appTitle` (34pt), `.body` (17pt), `.secondary` (15pt), `.caption` (13pt). Corner radius: `.radiusControl=12`, `.radiusCard=16`. |

### 4. Adjacent services (called during auth flows)

| # | File | Role |
|---|------|------|
| 15 | `Povver/Povver/Services/SessionManager.swift` | Stores `userId` in UserDefaults. Call `startSession(userId:)` after successful sign-in, `endSession()` on sign-out/delete. |
| 16 | `Povver/Povver/Services/DeviceManager.swift` | `registerCurrentDevice(for: userId)` — called during sign-up/sign-in. |
| 17 | `Povver/Povver/Services/TimezoneManager.swift` | `initializeTimezoneIfNeeded(userId:)` — called during sign-up/sign-in. |

### 5. Firebase Functions (no changes needed — verify understanding)

| # | File | Key fact |
|---|------|----------|
| 18 | `firebase_functions/functions/auth/middleware.js` | `verifyAuth()` calls `getAuth().verifyIdToken(idToken)` — provider-agnostic. Bearer tokens from Google/Apple sign-in work identically to email/password tokens. |
| 19 | `firebase_functions/functions/user/get-user.js` | Reads user doc. Does NOT reference `provider` field in any logic. |
| 20 | `firebase_functions/functions/user/update-user.js` | Updates preferences. `provider` is NOT in `allowedFields` — cannot be changed via this endpoint. |

### 6. Project config

| # | File | Key fact |
|---|------|----------|
| 21 | `Povver/Povver/GoogleService-Info.plist` | `CLIENT_ID`: `919326069447-02k61tnriomir3jd5ss8ig3befstdiik.apps.googleusercontent.com`. `REVERSED_CLIENT_ID`: `com.googleusercontent.apps.919326069447-02k61tnriomir3jd5ss8ig3befstdiik`. Project ID: `myon-53d85`. |

---

## Current Auth Flow Trace (Critical — SSO Must Follow This Pattern)

### Sign-Up (email)
```
RegisterView.performRegistration()
  → authService.signUp(email:, password:)
      → Auth.auth().createUser(withEmail:, password:)
      → Firestore write: users/{uid} { email, uid, created_at, provider: "email", week_starts_on_monday: true }
      → TimezoneManager.initializeTimezoneIfNeeded(userId:)
      → DeviceManager.registerCurrentDevice(for: userId)
  → session.startSession(userId: user.uid)
  → onRegister?(user.uid)                    // triggers flow = .main in RootView
```

### Sign-In (email)
```
LoginView.performLogin()
  → authService.signIn(email:, password:)
      → Auth.auth().signIn(withEmail:, password:)
      → TimezoneManager.initializeTimezoneIfNeeded(userId:)
      → DeviceManager.registerCurrentDevice(for: userId)
  → session.startSession(userId: user.uid)
  → onLogin?(user.uid)                       // triggers flow = .main in RootView
```

### SSO must follow the same post-auth sequence:
1. Authenticate with provider SDK → get Firebase credential
2. `Auth.auth().signIn(with: credential)` → Firebase creates auth user if new
3. Check `result.additionalUserInfo?.isNewUser`
4. If new: show confirmation dialog → on confirm: create Firestore user doc + timezone + device
5. If existing: timezone + device (user doc already exists)
6. `session.startSession(userId:)`
7. Call `onLogin?()` or `onRegister?()` callback → RootView switches to `.main`

---

## Research Findings: Firebase Auth Multi-Provider

### Provider IDs

Firebase uses these string identifiers for providers:
- `"password"` — email/password
- `"google.com"` — Google
- `"apple.com"` — Apple

**Important discrepancy**: The current `AuthService.signUp()` writes `"email"` as the `provider` value in Firestore, but Firebase's own provider ID is `"password"`. Keep writing `"email"` for email sign-ups (human-readable), write `"google.com"` / `"apple.com"` for SSO sign-ups. The `AuthProvider` enum's `rawValue` should match Firebase's IDs (for use with `providerData`, `unlink(fromProvider:)` etc.), but the Firestore `provider` field uses its own display-friendly values.

### One Account Per Email (Default Behavior)

Firebase enforces one account per email address. If a user signs up with email/password and later tries Google Sign-In with the same email, Firebase throws `accountExistsWithDifferentCredential`.

`fetchSignInMethodsForEmail()` is **deprecated** (email enumeration protection, mandatory since Sep 2023). We cannot query which providers an email uses. The error message must be generic.

### SSO Sign-In Mechanics

`Auth.auth().signIn(with: credential)` is the same call for both sign-in and sign-up with SSO — Firebase auto-creates the auth account if none exists. Check `result.additionalUserInfo?.isNewUser` to distinguish.

### Provider Linking / Unlinking

```swift
// Link a new provider to current user
currentUser.link(with: credential)          // throws if provider already linked elsewhere

// Unlink a provider
currentUser.unlink(fromProvider: "google.com")  // returns updated user
```

**Constraints the app must enforce:**
- `providerData.count > 1` before allowing unlink (Firebase doesn't enforce this)
- Warn user: unlinking a provider means signing in with it later creates a NEW account
- `currentUser.providerData` is the runtime source of truth

### Email Change

```swift
// Send verification to new email — actual change happens when user clicks the link
currentUser.sendEmailVerification(beforeUpdatingEmail: newEmail)
```

- Requires recent authentication (Firebase throws `requiresRecentLogin` if stale, ~5 min)
- Only meaningful for email/password users
- SSO users' emails come from the SSO provider — show greyed-out field

### Password Change / Set

```swift
// Change password (email/password users) — requires recent auth
currentUser.updatePassword(to: newPassword)

// Add password to SSO-only account — links email/password as new provider
let credential = EmailAuthProvider.credential(withEmail: currentUser.email!, password: newPassword)
currentUser.link(with: credential)
```

### Reauthentication

Required for: email change, password change, account deletion — when last sign-in is stale (~5 min).

```swift
// Email
let cred = EmailAuthProvider.credential(withEmail: email, password: password)
currentUser.reauthenticate(with: cred)

// Google — get fresh credential from Google SDK, then:
currentUser.reauthenticate(with: googleCredential)

// Apple — get fresh credential from ASAuthorization, then:
currentUser.reauthenticate(with: appleCredential)
```

### Apple Sign-In Specifics

1. **Email only on first sign-in.** Apple provides email and full name ONLY on the first authentication attempt. Subsequent sign-ins return only the user identifier. Capture and store email/name during the first sign-in. If you miss it, the data is gone.

2. **"Hide My Email" relay.** Users can hide their real email. Apple generates `xxx@privaterelay.appleid.com`. To send Firebase emails (password reset, verification) to relay addresses, register `noreply@myon-53d85.firebaseapp.com` with Apple's Private Email Relay service (manual step in Apple Developer portal).

3. **Token revocation (App Store requirement).** App Store guideline 5.1.1(v) requires account deletion when Sign in with Apple is offered. On deletion, call `Auth.auth().revokeToken(withAuthorizationCode:)` BEFORE `currentUser.delete()`. The `authorizationCode` is only available at sign-in time — store it in the user doc field `apple_authorization_code`.

4. **Implementation pattern.** Uses native `AuthenticationServices` — no third-party SDK. The `ASAuthorizationController` uses a delegate pattern that must be wrapped in `CheckedContinuation` for async/await. Requires a random nonce (32 chars) hashed with SHA256 — Firebase validates the nonce to prevent replay attacks.

### Google Sign-In Specifics

1. **SDK**: `GoogleSignIn` SPM package from `https://github.com/google/GoogleSignIn-iOS` (latest 7.x).
2. **URL scheme**: Register `REVERSED_CLIENT_ID` (`com.googleusercontent.apps.919326069447-02k61tnriomir3jd5ss8ig3befstdiik`) as a URL scheme in the Xcode project.
3. **URL handling**: Add `.onOpenURL { url in GIDSignIn.sharedInstance.handle(url) }` to the root view in `PovverApp.swift`.
4. **Presentation**: Google Sign-In requires a `UIViewController` to present its OAuth sheet. Create a helper to get the root VC from `UIApplication.shared.connectedScenes`.
5. **Email**: Google provides email on every sign-in (no first-time-only limitation).

### Account Deletion Sequence

```
1. Reauthenticate if needed (catch requiresRecentLogin)
2. If Apple provider is linked → Auth.auth().revokeToken(withAuthorizationCode: storedCode)
3. Delete all Firestore subcollections under users/{uid}
4. Delete the users/{uid} document
5. currentUser.delete()
6. SessionManager.shared.endSession()
7. Navigate to login screen
```

### Friendly Error Messages

| Firebase AuthErrorCode | User-facing message |
|----------------------|---------------------|
| `.wrongPassword` | "Incorrect password. Please try again." |
| `.requiresRecentLogin` | "For your security, please sign in again to continue." |
| `.emailAlreadyInUse` | "This email is already in use by another account." |
| `.weakPassword` | "Password must be at least 6 characters." |
| `.accountExistsWithDifferentCredential` | "An account with this email already exists. Please sign in with your original method, then link this provider in Settings." |
| `.invalidCredential` | "The sign-in credentials are invalid. Please try again." |
| `.networkError` | "Network error. Please check your connection and try again." |
| `.credentialAlreadyInUse` | "This {provider} account is already linked to a different Povver account." |
| `.userNotFound` | "No account found with this email. Please register first." |
| (any other) | "Something went wrong. Please try again." |

---

## Implementation Plan

### Phase 1: Auth Infrastructure (Models + AuthService)

Everything here is SSO-aware but testable with email-only accounts.

#### 1.1 Create `AuthProvider` enum
**New file**: `Povver/Povver/Models/AuthProvider.swift`

```swift
enum AuthProvider: String, CaseIterable {
    case email = "password"       // Firebase's internal ID for email/password
    case google = "google.com"
    case apple = "apple.com"
}
```

Properties: `displayName` ("Email" / "Google" / "Apple"), `icon` (SF Symbol: `"envelope"` / `"globe"` / `"apple.logo"`).

Static factory: `from(_ firebaseProviderId: String) -> AuthProvider?` — maps provider ID strings from `currentUser.providerData[].providerID`.

Note: `rawValue` matches Firebase's provider IDs so it works with `unlink(fromProvider:)` and `providerData` lookups. The Firestore `provider` field uses different display values (`"email"`, `"google.com"`, `"apple.com"`).

#### 1.2 Add `apple_authorization_code` to User model
**Modify**: `Povver/Povver/Models/User.swift`

Add `var appleAuthorizationCode: String?` with CodingKey `"apple_authorization_code"`. Safe — optional field, existing accounts decode it as nil.

#### 1.3 Extend AuthService with account management
**Modify**: `Povver/Povver/Services/AuthService.swift`

**Refactor first**: Extract user doc creation from `signUp()` into a shared method:
```swift
func createUserDocument(userId: String, email: String, provider: String, name: String? = nil, appleAuthCode: String? = nil) async throws
```

This writes the same fields as current `signUp()` but accepts provider as parameter. Existing `signUp()` calls it with `provider: "email"`. SSO will call it with `"google.com"` or `"apple.com"`.

**Add these methods:**

| Method | Signature | Implementation |
|--------|-----------|----------------|
| `linkedProviders` | `var linkedProviders: [AuthProvider]` (computed) | Map `currentUser?.providerData` through `AuthProvider.from()` |
| `friendlyAuthError` | `static func friendlyAuthError(_ error: Error) -> String` | Switch on `(error as NSError).code` using `AuthErrorCode` values, return friendly string |
| `changeEmail` | `func changeEmail(to newEmail: String) async throws` | `currentUser.sendEmailVerification(beforeUpdatingEmail: newEmail)` |
| `changePassword` | `func changePassword(currentPassword: String, newPassword: String) async throws` | Reauthenticate with email cred, then `currentUser.updatePassword(to:)` |
| `setPassword` | `func setPassword(_ password: String) async throws` | `currentUser.link(with: EmailAuthProvider.credential)` — adds email/password provider to SSO account |
| `reauthenticateWithEmail` | `func reauthenticateWithEmail(password: String) async throws` | `currentUser.reauthenticate(with: EmailAuthProvider.credential)` |
| `linkProvider` | `func linkProvider(_ credential: AuthCredential) async throws` | `currentUser.link(with: credential)` |
| `unlinkProvider` | `func unlinkProvider(_ provider: AuthProvider) async throws` | Guard `providerData.count > 1`, then `currentUser.unlink(fromProvider: provider.rawValue)` |
| `deleteAccount` | `func deleteAccount() async throws` | Full sequence: revoke Apple token if applicable → `UserRepository.shared.deleteUser()` → `currentUser.delete()` → `SessionManager.shared.endSession()` |

#### 1.4 Fix UserRepository.deleteUser
**Modify**: `Povver/Povver/Repositories/UserRepository.swift` — line 89

Current broken list:
```swift
let subcollections = ["user_attributes", "linked_devices", "workouts", "workout_templates"]
```

Fix to (from Firestore schema security rules, line 882):
```swift
let subcollections = [
    "user_attributes", "linked_devices", "workouts", "templates",
    "routines", "active_workouts", "canvases", "progress_reports",
    "weekly_stats", "analytics_series_exercise", "analytics_series_muscle",
    "analytics_rollups", "analytics_state"
]
```

Note: Firestore client SDK `getDocuments()` on a subcollection with many documents may need batching. For canvas subcollections (`cards`, `up_next`, `events`, `idempotency`), these are nested under `canvases/{id}/` — the current approach of deleting the `canvases` collection deletes the parent docs but **not** their nested subcollections. Consider whether to recursively delete canvas subcollections or accept that orphaned nested docs get cleaned up later. For MVP, deleting the parent docs is acceptable — orphaned subcollections without a parent are inaccessible.

---

### Phase 2: Account Management UI

All views work with email-only accounts. They read `linkedProviders` to adapt behavior — for email-only users this is `[.email]`, so all email code paths are testable immediately. SSO code paths (greyed-out email, "Set Password" mode) render correctly but SSO operations are wired in Phases 3-4.

#### 2.1 Create ReauthenticationView
**New file**: `Povver/Povver/Views/Settings/ReauthenticationView.swift`

Sheet presented when a sensitive operation requires fresh credentials. Uses `SheetScaffold`.

**Init params**: `providers: [AuthProvider]`, `onSuccess: () -> Void`

**Layout**: Title "Verify It's You" + subtitle "For your security, please sign in again". Shows reauthentication options based on `providers`:
- `.email` → `SecureField` for password + "Verify" `PovverButton(.primary)`
- `.google` → "Verify with Google" `PovverButton(.secondary, leadingIcon: globe)` — non-functional until Phase 3
- `.apple` → "Verify with Apple" `PovverButton(.secondary, leadingIcon: apple.logo)` — non-functional until Phase 4

Error display: text below buttons in `.caption` / `.destructive`.

On successful reauth: call `onSuccess()` and dismiss.

#### 2.2 Create EmailChangeView
**New file**: `Povver/Povver/Views/Settings/EmailChangeView.swift`

Sheet using `SheetScaffold`. Init params: `hasEmailProvider: Bool`, `providerDisplayName: String`.

**Two states:**

A) `hasEmailProvider == false` (SSO-only):
- Show current email greyed out (`.textTertiary`)
- Caption below: "Changing email is not possible when signed in with {providerDisplayName}"
- Done button dismisses

B) `hasEmailProvider == true`:
- Text field for new email (use `authTextField` pattern from LoginView — or inline equivalent)
- "Send Verification" button → `authService.changeEmail(to:)`
- On success: switch to confirmation state showing "Verification email sent to {newEmail}. Check your inbox and click the link to complete the change."
- On `requiresRecentLogin` error: present `ReauthenticationView`, then retry

#### 2.3 Create PasswordChangeView
**New file**: `Povver/Povver/Views/Settings/PasswordChangeView.swift`

Sheet using `SheetScaffold`. Init param: `hasEmailProvider: Bool`.

**Change mode** (`hasEmailProvider == true`):
- Fields: Current Password, New Password, Confirm Password
- Validation: new password >= 6 chars, new == confirm
- Action: `authService.changePassword(currentPassword:, newPassword:)`

**Set mode** (`hasEmailProvider == false`):
- Title: "Set Password" (not "Change Password")
- Fields: New Password, Confirm Password (no current password — they don't have one)
- Action: `authService.setPassword(newPassword)` — this links email/password as a provider
- On success: show brief confirmation, dismiss

#### 2.4 Create LinkedAccountsView
**New file**: `Povver/Povver/Views/Settings/LinkedAccountsView.swift`

Full-screen view (NavigationLink destination, not a sheet).

**Linked providers section:**
- List each provider from `authService.linkedProviders` as a row with icon + name + checkmark
- Each row has "Unlink" button, BUT:
  - Hidden if only 1 provider is linked
  - When only 1: show text "You need at least one sign-in method. Link another method before unlinking."
- Unlink flow: `.confirmationDialog` → "If you unlink {provider}, you won't be able to sign in with it anymore. Are you sure?" → `authService.unlinkProvider()`

**Available to link section:**
- Show `PovverButton(.secondary)` for each provider NOT in `linkedProviders`:
  - "Link Google" (non-functional until Phase 3)
  - "Link Apple" (non-functional until Phase 4)
  - "Set Password" → opens `PasswordChangeView(hasEmailProvider: false)` (functional now)

#### 2.5 Create DeleteAccountView
**New file**: `Povver/Povver/Views/Settings/DeleteAccountView.swift`

Full-screen view (NavigationLink destination).

**Layout:**
- Warning icon + "Delete Account" title in `.destructive` color
- Text: "This action cannot be undone. All your data will be permanently deleted:"
- List of items: workout history and templates, progress and analytics, AI coach memories, profile and account data
- `PovverButton("Delete My Account", style: .destructive)`

**Flow:**
1. Tap delete → present `ReauthenticationView(providers: linkedProviders)`
2. On reauth success → show `.confirmationDialog`: "This will permanently delete your account and all data. This cannot be undone." with "Delete Everything" (destructive) and "Cancel"
3. On confirm → `authService.deleteAccount()` → navigate back to login (need to set `flow = .login` — pass a callback or use `AuthService.isAuthenticated` to trigger RootView)

**Edge case**: If `deleteAccount()` throws `requiresRecentLogin` despite reauthentication (race condition), catch and re-present reauth.

#### 2.6 Update ProfileView
**Modify**: `Povver/Povver/Views/Tabs/ProfileView.swift`

**Add state:**
```swift
@State private var linkedProviders: [AuthProvider] = []
@State private var showingEmailChange = false
@State private var showingPasswordChange = false
```

**Modify Account section — Email row:**
- If `linkedProviders.contains(.email)`: tappable (chevron), opens `EmailChangeView(hasEmailProvider: true, ...)`
- Else: not tappable, shows caption "Email is managed by {provider name}" in `.textTertiary`

**Add Security section** (insert between Preferences and More sections):
```
sectionHeader("Security")

VStack(spacing: 0) {
    NavigationLink → LinkedAccountsView
        ProfileRowLinkContent(icon: "lock.shield", title: "Linked Accounts",
            subtitle: "{N} sign-in method(s)")

    Divider

    Button → showingPasswordChange = true
        ProfileRowLinkContent(icon: "key",
            title: linkedProviders.contains(.email) ? "Change Password" : "Set Password",
            subtitle: linkedProviders.contains(.email) ? "Update your password" : "Add email sign-in")

    Divider

    NavigationLink → DeleteAccountView
        ProfileRowLinkContent(icon: "trash", title: "Delete Account",
            subtitle: "Permanently delete your account")
}
// .background, .clipShape, .padding — same pattern as other sections
```

**Update `loadProfile()`**: Add `linkedProviders = authService.linkedProviders` after loading user data.

**Add sheet modifiers:**
```swift
.sheet(isPresented: $showingEmailChange) {
    EmailChangeView(hasEmailProvider: linkedProviders.contains(.email),
                    providerDisplayName: /* primary non-email provider name */)
}
.sheet(isPresented: $showingPasswordChange) {
    PasswordChangeView(hasEmailProvider: linkedProviders.contains(.email))
}
```

---

### Phase 3: Google Sign-In

#### 3.1 SPM dependency
Add `GoogleSignIn` from `https://github.com/google/GoogleSignIn-iOS` (7.x) to the Xcode project.

#### 3.2 URL scheme
Add `com.googleusercontent.apps.919326069447-02k61tnriomir3jd5ss8ig3befstdiik` as a URL scheme (Xcode → target → Info → URL Types).

#### 3.3 App entry point
**Modify**: `Povver/Povver/PovverApp.swift`

Add to `WindowGroup`:
```swift
.onOpenURL { url in
    GIDSignIn.sharedInstance.handle(url)
}
```

#### 3.4 Root VC helper
**New file**: `Povver/Povver/Extensions/UIApplication+RootVC.swift`

```swift
extension UIApplication {
    var rootViewController: UIViewController? {
        connectedScenes
            .compactMap { $0 as? UIWindowScene }
            .flatMap { $0.windows }
            .first { $0.isKeyWindow }?
            .rootViewController
    }
}
```

#### 3.5 Google methods in AuthService
**Modify**: `Povver/Povver/Services/AuthService.swift`

Three methods, all following the same pattern — get Google credential, then use it differently:

| Method | Firebase call |
|--------|-------------|
| `signInWithGoogle(presenting: UIViewController) async throws -> (isNewUser: Bool, user: FirebaseAuth.User)` | `Auth.auth().signIn(with: credential)` |
| `reauthenticateWithGoogle(presenting: UIViewController) async throws` | `currentUser.reauthenticate(with: credential)` |
| `linkGoogle(presenting: UIViewController) async throws` | `currentUser.link(with: credential)` |

Core Google credential flow (shared):
```swift
let result = try await GIDSignIn.sharedInstance.signIn(withPresenting: viewController)
guard let idToken = result.user.idToken?.tokenString else { throw ... }
let credential = GoogleAuthProvider.credential(withIDToken: idToken,
                                                accessToken: result.user.accessToken.tokenString)
```

#### 3.6 Wire Google in LoginView and RegisterView
**Modify**: `Povver/Povver/Views/LoginView.swift`, `Povver/Povver/Views/RegisterView.swift`

Replace Google stub buttons. Add state:
```swift
@State private var showingNewAccountConfirmation = false
@State private var pendingSSOUser: FirebaseAuth.User?
@State private var pendingSSOProvider: String?  // "google.com" or "apple.com"
@State private var pendingSSOEmail: String?
@State private var pendingSSOName: String?
@State private var pendingSSOAuthCode: String?  // Apple only
```

Google button action:
```swift
PovverButton("Sign in with Google", style: .secondary, leadingIcon: Image(systemName: "globe")) {
    Task { await performGoogleSignIn() }
}
```

`performGoogleSignIn()`:
1. Get root VC via `UIApplication.shared.rootViewController`
2. Call `authService.signInWithGoogle(presenting: vc)`
3. If `isNewUser`: save pending state, set `showingNewAccountConfirmation = true`
4. If NOT new user: `session.startSession(userId:)` → `onLogin?(userId)`
5. On error: `errorMessage = AuthService.friendlyAuthError(error)`

Confirmation dialog (add as modifier to body):
```swift
.confirmationDialog("Create New Account?", isPresented: $showingNewAccountConfirmation) {
    Button("Create Account") { Task { await confirmNewAccount() } }
    Button("Cancel", role: .cancel) { Task { await cancelNewAccount() } }
} message: {
    Text("You are creating a new Povver account with \(pendingSSOProvider == "google.com" ? "Google" : "Apple"). Continue?")
}
```

`confirmNewAccount()`: call `authService.createUserDocument(...)` → `session.startSession()` → `onLogin?()`

`cancelNewAccount()`: call `try? await pendingSSOUser?.delete()` to remove the auto-created auth record. Clear pending state. No error shown.

#### 3.7 Wire Google into settings views
**Modify**: `LinkedAccountsView.swift` — "Link Google" button calls `authService.linkGoogle(presenting:)`
**Modify**: `ReauthenticationView.swift` — "Verify with Google" button calls `authService.reauthenticateWithGoogle(presenting:)`

---

### Phase 4: Apple Sign-In

#### 4.1 Xcode capability
Add "Sign in with Apple" in Signing & Capabilities. This auto-creates the entitlements file.

#### 4.2 Create AppleSignInCoordinator
**New file**: `Povver/Povver/Services/AppleSignInCoordinator.swift`

Wraps Apple's delegate-based `ASAuthorizationController` in async/await.

```swift
class AppleSignInCoordinator: NSObject, ASAuthorizationControllerDelegate,
                               ASAuthorizationControllerPresentationContextProviding {
    private var continuation: CheckedContinuation<ASAuthorizationAppleIDCredential, Error>?

    func signIn(nonce: String) async throws -> ASAuthorizationAppleIDCredential {
        try await withCheckedThrowingContinuation { continuation in
            self.continuation = continuation
            let request = ASAuthorizationAppleIDProvider().createRequest()
            request.requestedScopes = [.email, .fullName]
            request.nonce = sha256(nonce)
            let controller = ASAuthorizationController(authorizationRequests: [request])
            controller.delegate = self
            controller.presentationContextProvider = self
            controller.performRequests()
        }
    }

    // Delegate methods resume the continuation with success/failure
    // sha256() helper hashes the nonce string
    // randomNonceString() generates a 32-char cryptographic nonce
}
```

The coordinator must be retained (stored as a property) for the duration of the sign-in flow — it's the delegate.

#### 4.3 Apple methods in AuthService
**Modify**: `Povver/Povver/Services/AuthService.swift`

| Method | Firebase call |
|--------|-------------|
| `signInWithApple() async throws -> (isNewUser: Bool, user: FirebaseAuth.User, email: String?, authCode: String?)` | `Auth.auth().signIn(with: credential)` |
| `reauthenticateWithApple() async throws` | `currentUser.reauthenticate(with: credential)` |
| `linkApple() async throws` | `currentUser.link(with: credential)` |

Core Apple credential flow:
```swift
let nonce = randomNonceString()
let coordinator = AppleSignInCoordinator()
let appleCredential = try await coordinator.signIn(nonce: nonce)
guard let identityToken = appleCredential.identityToken,
      let tokenString = String(data: identityToken, encoding: .utf8) else { throw ... }
let credential = OAuthProvider.credential(withProviderID: "apple.com",
                                           idToken: tokenString, rawNonce: nonce)
let email = appleCredential.email  // nil on subsequent sign-ins
let authCode = appleCredential.authorizationCode.flatMap { String(data: $0, encoding: .utf8) }
```

**Update `deleteAccount()`**: Before deleting, check if Apple is a linked provider. If so, fetch stored `apple_authorization_code` from user doc and call `Auth.auth().revokeToken(withAuthorizationCode:)`.

**Store coordinator as instance property** on AuthService to keep it alive during the async flow.

#### 4.4 Wire Apple in LoginView and RegisterView
**Modify**: `Povver/Povver/Views/LoginView.swift`, `Povver/Povver/Views/RegisterView.swift`

Same pattern as Google. Replace Apple stub. `performAppleSignIn()` calls `authService.signInWithApple()`, handles `isNewUser` with the same confirmation dialog. On confirm, `createUserDocument()` includes `appleAuthCode` parameter.

#### 4.5 Wire Apple into settings views
**Modify**: `LinkedAccountsView.swift` — "Link Apple" calls `authService.linkApple()`
**Modify**: `ReauthenticationView.swift` — "Verify with Apple" calls `authService.reauthenticateWithApple()`

---

### Phase 5: Documentation

| File | Update |
|------|--------|
| `docs/FIRESTORE_SCHEMA.md` | Add `apple_authorization_code: string?` to `users/{uid}` schema |
| `docs/IOS_ARCHITECTURE.md` | Add section on authentication: supported providers, SSO flow, account management, provider linking |
| `Povver/Povver/Views/Settings/ARCHITECTURE.md` (new) | Tier-2 doc for the Settings module: file list, view responsibilities, navigation structure |

---

## File Manifest

### New files

| File | Phase |
|------|-------|
| `Povver/Povver/Models/AuthProvider.swift` | 1 |
| `Povver/Povver/Views/Settings/ReauthenticationView.swift` | 2 |
| `Povver/Povver/Views/Settings/EmailChangeView.swift` | 2 |
| `Povver/Povver/Views/Settings/PasswordChangeView.swift` | 2 |
| `Povver/Povver/Views/Settings/LinkedAccountsView.swift` | 2 |
| `Povver/Povver/Views/Settings/DeleteAccountView.swift` | 2 |
| `Povver/Povver/Extensions/UIApplication+RootVC.swift` | 3 |
| `Povver/Povver/Services/AppleSignInCoordinator.swift` | 4 |
| `Povver/Povver/Views/Settings/ARCHITECTURE.md` | 5 |

### Modified files

| File | Phase(s) | What changes |
|------|----------|-------------|
| `Povver/Povver/Models/User.swift` | 1 | Add `appleAuthorizationCode` optional field |
| `Povver/Povver/Services/AuthService.swift` | 1, 3, 4 | Phase 1: refactor + account mgmt methods. Phase 3: Google methods. Phase 4: Apple methods + token revocation. |
| `Povver/Povver/Repositories/UserRepository.swift` | 1 | Fix `deleteUser()` subcollection list |
| `Povver/Povver/Views/Tabs/ProfileView.swift` | 2 | Add Security section, adapt email row |
| `Povver/Povver/Views/LoginView.swift` | 3, 4 | Phase 3: Google button + SSO confirmation flow. Phase 4: Apple button. |
| `Povver/Povver/Views/RegisterView.swift` | 3, 4 | Same as LoginView |
| `Povver/Povver/PovverApp.swift` | 3 | Add `.onOpenURL` for Google |
| `Povver/Povver/Views/Settings/LinkedAccountsView.swift` | 3, 4 | Wire Google link, then Apple link |
| `Povver/Povver/Views/Settings/ReauthenticationView.swift` | 3, 4 | Wire Google reauth, then Apple reauth |
| `docs/FIRESTORE_SCHEMA.md` | 5 | Add field to users schema |
| `docs/IOS_ARCHITECTURE.md` | 5 | Add auth providers section |

### Config changes (manual / Xcode UI)

| Change | Phase |
|--------|-------|
| SPM: add `GoogleSignIn` from `https://github.com/google/GoogleSignIn-iOS` | 3 |
| URL Types: add `com.googleusercontent.apps.919326069447-02k61tnriomir3jd5ss8ig3befstdiik` | 3 |
| Capability: "Sign in with Apple" | 4 |
| Firebase Console: enable Google sign-in provider | 3 |
| Firebase Console: enable Apple sign-in provider | 4 |
| Apple Developer: register Firebase email domain with Private Email Relay | 4 |

---

## Verification Checklist

### After Phases 1-2 (email-only account management)

- [ ] Build succeeds: `xcodebuild -scheme Povver -destination 'platform=iOS Simulator,name=iPhone 16 Pro' build`
- [ ] Profile > Account > Email row is tappable for email users → opens EmailChangeView
- [ ] EmailChangeView: enter new email → "Send Verification" → success state shown
- [ ] Profile > Security section visible with 3 rows
- [ ] Change Password: enter current + new + confirm → success
- [ ] Linked Accounts: shows "Email" as linked, Google/Apple as available (buttons present, non-functional)
- [ ] Linked Accounts: unlink button hidden when only 1 provider, with explanation text
- [ ] Delete Account: warning screen → reauthenticate with password → final confirm → account deleted
- [ ] After delete: user is on login screen, Firebase Console shows user gone from Auth and Firestore

### After Phase 3 (Google Sign-In)

- [ ] Login screen: Google button → OAuth sheet → new user → "Create account?" confirmation → confirm → main screen
- [ ] User doc in Firestore has `provider: "google.com"`
- [ ] Sign out → Google button (same account) → straight to main (no confirmation)
- [ ] Google button → cancel confirmation → back to login, no user doc created, no error
- [ ] Email user → sign out → Google with same email → friendly collision error message
- [ ] Profile > email row greyed out with "Email is managed by Google" for Google-only user
- [ ] Linked Accounts > Link Google → success, shows as linked
- [ ] Linked Accounts > Unlink Google (email still linked) → warning → confirm → unlinked
- [ ] Reauthenticate with Google in delete flow → works

### After Phase 4 (Apple Sign-In)

- [ ] Same matrix as Google tests above, but with Apple
- [ ] First Apple sign-in: email captured in user doc (check Firestore)
- [ ] `apple_authorization_code` stored in user doc
- [ ] Delete account with Apple provider: token revocation called before deletion
- [ ] "Hide My Email" relay address stored correctly (if testable — requires real device)
