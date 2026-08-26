# Auto-select framework (Step 1.5 deep dive)

The full decision tree for `mobile-app-dev` Step 1.5. This is the
canonical source; `SKILL.md` summarizes the algorithm; this document
shows every branch and the rationale.

---

## Inputs

1. **Requirements checklist** (`templates/requirements_checklist.md`)
   filled in from Step 0.
2. **Team profile** (additional fields in the checklist):
   - Languages the team is fluent in: Swift / Kotlin / Dart / TypeScript / C#.
   - Existing codebases: native iOS / native Android / React / Flutter / .NET / web.
   - Hiring pipeline / budget for new languages.
3. **Hard constraints** from the requirements:
   - Required OS frameworks (e.g., HealthKit, ARKit, Compose).
   - Distribution channel (App Store / Play Store / MDM / sideload).
   - Compliance / regulatory.
4. **Soft preferences** from the user:
   - Performance budget vs development speed.
   - Native feel vs cross-platform polish.
   - Time-to-market.

## Algorithm (deterministic)

The algorithm has 5 phases. Each phase may produce a final answer
(return immediately) or pass through to the next.

### Phase 1 -- Game / out-of-scope gate

```
IF category == D (game / interactive) OR category == (any non-mobile):
    RETURN "Game engine (Unity / Unreal / Godot). Out of scope for this skill."
    STOP.
```

If the request is for a game, route to a game-engine skill. Do not
proceed.

### Phase 2 -- Hard native constraints

A "hard constraint" means the framework is **forced** by a platform
feature that cannot be reasonably implemented cross-platform.

```
HARD_NATIVE = (
    REQUIRED_FEATURE in {Widget, LiveActivity, AppIntent, CarPlay,
                         HealthKit, ARKit, RealityKit, CallKit,
                         WatchFace, visionOS-SpatialUI, Metal,
                         SecureEnclave, StrongBox, HardwareBackedKeystore}
    OR REQUIRED_FEATURE in {WearOS-Tile, AndroidAuto,
                            ForegroundService-with-foregroundServiceType}
)

IF HARD_NATIVE AND target == iOS-only:
    RETURN "Swift + SwiftUI (iOS-only delivery, hard native constraint)."
    STOP.

IF HARD_NATIVE AND target == Android-only:
    RETURN "Kotlin + Compose (Android-only delivery, hard native constraint)."
    STOP.

IF HARD_NATIVE AND target == iOS + Android:
    RETURN "Two native codebases: Swift + SwiftUI (iOS) AND
            Kotlin + Compose (Android). Cross-platform options
            are NOT viable for these features."
    STOP.
```

The "hard native" features list is exhaustive of features that:
- Cannot be implemented from cross-platform at all, OR
- Have only token cross-platform implementations that look bad and
  miss the point.

### Phase 3 -- Cross-platform criteria

If the requirements call for both platforms AND the team is OK with
cross-platform, choose by these criteria (in order):

```
IF both_platforms_required AND custom_UI_or_animation_intensive:
    RETURN "Flutter."
    STOP.

IF both_platforms_required AND team_is_web_first:
    RETURN "React Native."
    STOP.

IF both_platforms_required AND huge_JS_library_surface:
    # Stripe, Mapbox, Auth0, Segment, Branch, etc.
    RETURN "React Native."
    STOP.

IF both_platforms_required AND team_is_dotnet_first:
    RETURN ".NET MAUI."
    STOP.

IF both_platforms_required AND native_UI_mandated_by_design:
    # Cannot compromise look-and-feel; must have native widgets.
    RETURN "Kotlin Multiplatform (shared business logic, native UI)."
    STOP.

IF existing_web_app_to_wrap:
    RETURN "Capacitor or Tauri Mobile."
    STOP.
```

### Phase 4 -- Team / existing codebase override

After Phase 3 picks a framework, check if the team can actually
deliver it. The override is **applied**, not skipped:

```
SELECTED = result_of_phase_3_or_phase_2

IF SELECTED in {Swift, Swift + SwiftUI} AND no_swift_team:
    SWAP to Flutter or React Native.
    LOG override reason.

IF SELECTED in {Kotlin, Kotlin + Compose} AND no_kotlin_team:
    SWAP to Flutter or React Native or .NET MAUI.
    LOG override reason.

IF existing_typescript_react_codebase:
    PREFER React Native over other cross-platform.
    LOG override reason.

IF existing_csharp_xaml_codebase:
    PREFER .NET MAUI over other cross-platform.
    LOG override reason.

IF existing_dart_flutter_codebase:
    PREFER Flutter over other cross-platform.
    LOG override reason.
```

The overrides are conservative: a Phase 2 hard-native constraint is
**never** overridden. Only Phase 3 picks get swapped.

### Phase 5 -- Single-platform default

If the request is single-platform (only iOS or only Android) and not
yet decided:

```
IF target == iOS-only:
    RETURN "Swift + SwiftUI (default). UIKit only if existing
            codebase requires it or specific control is missing
            in SwiftUI."

IF target == Android-only:
    RETURN "Kotlin + Compose (default). XML Views only if existing
            codebase requires it."

IF target == watchOS-only OR target == visionOS-only:
    RETURN "Swift + SwiftUI (mandatory; no alternative for these
            platforms)."
```

## Output schema

After running the algorithm, the agent records the result in
`requirements.md`:

```markdown
## Step 1.5 result

Selected framework: Kotlin + Compose
Rationale:
  - Single-platform Android (requirement 3.1) per Phase 5.
  - No hard native constraints triggered.
  - Team has Kotlin experience (team profile: 3 Kotlin devs).
Alternatives considered:
  - Flutter: rejected because no Dart team, would require
    significant retraining (cost > benefit for this app).
  - React Native: rejected because no web team and custom
    Compose Material 3 design would not translate well.
Confidence: HIGH.
Override applied: no.
```

## Confidence levels

| Level      | When                                                      |
|------------|-----------------------------------------------------------|
| **HIGH**   | Phase 2 hard-native constraint matched, OR single-platform default. |
| **MEDIUM** | Phase 3 cross-platform criterion matched, team OK.        |
| **LOW**    | Phase 3 + Phase 4 swap applied (override), OR no clear winner. |

**LOW confidence must trigger a follow-up question to the user**
before proceeding to Step 2.

## Worked examples

### Example 1 -- QR scanner (iOS)

- Category: A. Utility.
- Single platform: iOS 16+.
- Required: camera, torch.
- Team: Swift-fluent.

Phase 1: not a game.
Phase 2: no hard native features (camera + torch are accessible via
plugins in Flutter / RN, but here the team is iOS-only so single-platform
default kicks in).
Phase 3: not applicable (single-platform).
Phase 4: not applicable.
Phase 5: iOS-only -> **Swift + SwiftUI**.
Confidence: HIGH.

### Example 2 -- Field-service CRM (iOS + Android)

- Category: B. Productivity / LOB.
- Both platforms: yes.
- Required: camera, location, push, offline-first.
- Team: 4 web devs (TypeScript), no Swift/Kotlin.
- Existing codebase: TypeScript / React web app.

Phase 1: not a game.
Phase 2: no hard native features.
Phase 3: cross-platform criteria -> not "custom UI" heavy; team is
web-first -> **React Native**.
Phase 4: existing TS codebase -> PREFER React Native (already there).
Confidence: MEDIUM.

### Example 3 -- Apple Watch fitness app

- Category: F. Finance / health.
- Single platform: watchOS 10+.
- Required: HealthKit, Workout, Watch face complication.

Phase 1: not a game.
Phase 2: HealthKit, Watch face -> HARD_NATIVE.
Phase 5: watchOS-only -> **Swift + SwiftUI** (no alternative for
watchOS).
Confidence: HIGH.

### Example 4 -- News aggregator (iOS + Android)

- Category: C. Social / community.
- Both platforms: yes.
- Required: push, no specific OS frameworks.
- Team: 2 Swift + 2 Kotlin, prefers "shipped last week" feel.
- Existing codebase: none.

Phase 1: not a game.
Phase 2: no hard native features.
Phase 3: cross-platform criteria -> news UI is mostly standard lists
and detail screens, no heavy custom animation. Either Flutter or RN
would work. No web team. No .NET team. -> **Flutter** (best default for
non-web team).
Phase 4: no override.
Confidence: MEDIUM (could go either Flutter or RN).

### Example 5 -- Banking app (iOS + Android)

- Category: F. Finance / health.
- Both platforms: yes.
- Required: FaceID / TouchID, Secure Enclave / Keystore, push.
- Compliance: PCI DSS, GDPR.

Phase 1: not a game.
Phase 2: Secure Enclave / StrongBox hardware-backed key storage is in
the hard-native list -> **two native codebases** (Swift + SwiftUI for
iOS, Kotlin + Compose for Android).
Phase 3: not applicable after the Phase 2 hard constraint.
Phase 4: team profile says "no preference, will hire"; Phase 2 is never
overridden.
Confidence: HIGH.

## Edge cases

### Single-platform delivery on the wrong OS

If the user asks for an Android app but only the iOS team is available,
Phase 5 returns Kotlin + Compose (per requirements), and Phase 4
swaps to Flutter. Document the swap in `showstoppers` so the next
run respects it.

### "Mobile + Web" requirements

If the requirements call for both a mobile app and a web app:
- Phase 1 -> 5 runs against the **mobile** part.
- Web app is a separate skill (web-app skill).

### "Mobile + Backend" requirements

Same: backend is a separate skill. The mobile skill handles the API
client (Retrofit / Dio / axios), not the API server.

### Hybrid cross-platform + native

Kotlin Multiplatform with Compose Multiplatform covers shared UI
across iOS + Android. The algorithm picks it when:
- Phase 3.4 ("native UI mandated by design") matches.
- Team has Kotlin experience.

For SwiftUI + UIKit side of KMP, KMP can also use SwiftUI through
the `kotlinx.coroutines` interop. But this is rare in production.

## Anti-patterns

- **Picking React Native because "we have a web team"** -- if the app
  is heavy on animation, Flutter will look better and run smoother.
- **Picking Flutter for a 1-screen utility** -- the cross-platform
  overhead is not justified; go native.
- **Picking .NET MAUI without a .NET team** -- learn curve is high.
- **Refusing to override Phase 5** -- if the user has a strategic
  reason (existing team, existing codebase), respect it and document.
- **Trusting the algorithm blindly** -- LOW confidence results need
  a human review.
