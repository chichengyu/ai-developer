# Task decomposition (deep dive)

Step 0 + Step 3 of the SKILL.md workflow. Read this when the
requirements checklist is filled in and you are about to break the work
into verifiable cards.

## The principle

Every task card must be:

- **Deliverable-shaped** -- produces something visible or buildable.
- **Independently testable** -- one acceptance criterion per card.
- **Bounded** -- 0.5 to 1 engineer-day. Larger cards split.
- **Discoverable** -- one DAG edge between two cards implies a real
  dependency, not a soft ordering preference.

## Worked example 1 -- Category A utility (QR scanner)

### Step 0 outcome (excerpt)

- 1.5: Offline-first required: yes (cache last scan locally).
- 3.1: App Store public release: yes.
- 4.5: Minimum iOS 16, Android 9 (API 28).
- 5.2: Permission denied -- show "open settings" button.

### Step 3 cards

| ID    | Title                                      | Owner | Est. | Depends on        | Acceptance                                          |
|-------|--------------------------------------------|-------|------|-------------------|------------------------------------------------------|
| T-001 | Vision + Camera permission Info.plist keys | @a    | 0.5d | --                | Info.plist builds with no warnings.                  |
| T-002 | `AVCaptureSession` setup + preview layer   | @a    | 1d   | T-001             | Preview visible at 30+ FPS on iPhone 12.             |
| T-003 | Barcode detector wrapper (AVCaptureMetadataOutput) | @a | 1d | T-002          | Scans QR code in test image in < 500 ms.            |
| T-004 | `ScanResult` model + local store (SwiftData / Room) | @b | 1d | --             | Persists a ScanResult, survives kill+restart.        |
| T-005 | Result list screen                        | @b    | 1d   | T-003, T-004      | List shows last 50 scans, sorted by time.            |
| T-006 | Permission request flow with settings deep link | @b | 0.5d | T-001          | Denied -> "Open Settings" button works.              |
| T-007 | Crashlytics SDK init in app launch        | @c    | 0.5d | --                | Crash report shows in Firebase console.              |
| T-008 | TestFlight + Play internal upload         | @c    | 1d   | T-001..T-007      | Build in CI, uploaded, link works.                   |

Total: 6.5 engineer-days. Matches reality for a one-engineer-team.

## Worked example 2 -- Category B LOB (internal CRM)

### Step 0 outcome (excerpt)

- 1.5: Offline-first required: partial (read-only when offline).
- 3.4: Enterprise MDM via Intune.
- 4.2: Backend is internal REST with OAuth client-credentials.
- 5.1: Offline behavior: read cached data + greyed-out actions.

### Step 3 cards

| ID    | Title                                | Est. | Depends on | Acceptance |
|-------|--------------------------------------|------|------------|------------|
| T-001 | Backend auth + token refresh module  | 1d   | --         | 401 -> retry -> 200 in test. |
| T-002 | Customer list screen + pagination    | 1d   | T-001      | Loads 1000 customers, 50/page, scrolls in 16 ms/frame. |
| T-003 | Customer detail screen               | 1d   | T-001      | Loads single customer in < 200 ms. |
| T-004 | Offline cache (Core Data / Room)     | 1d   | T-001      | Cold-start with airplane mode shows last 50. |
| T-005 | Edit customer form                   | 1d   | T-003      | Optimistic UI; rollback on server error. |
| T-006 | MDM Intune App SDK integration       | 1d   | --         | App launches wrapped, SDK does not break tests. |
| T-007 | App config via remote feature flag   | 0.5d | T-001      | Toggle in LaunchDarkly changes UI behavior. |
| T-008 | Crash + analytics instrumentation    | 0.5d | T-002      | Synthetic crash appears in Crashlytics. |
| T-009 | Fastlane lanes (beta + release)      | 1d   | T-002, T-008 | `fastlane ios beta` and `fastlane android beta` succeed. |

## Worked example 3 -- Category C social (chat)

Chat apps have a real-time component that other categories do not. Add:

| ID    | Title                                | Est. | Depends on |
|-------|--------------------------------------|------|------------|
| T-010 | WebSocket transport (URLSessionWebSocketTask) | 1d | T-001 |
| T-011 | Message model + IndexedDB / SwiftData | 1d | T-001 |
| T-012 | Channel list + push-to-channel routing | 1d | T-010, T-011 |
| T-013 | Background push for new messages     | 0.5d | -- |
| T-014 | Read receipts + typing indicators    | 0.5d | T-010 |
| T-015 | Media attachment (photo + file)      | 1d   | T-010, T-011 |

## How to keep cards small

If a card feels too big, split it on one of these seams:

1. **Data layer vs UI layer** -- "build the model + repository" is
   one card; "build the screen that displays it" is another.
2. **Happy path vs edge cases** -- "happy path" is one card; each
   edge case (offline, denied permission, server error) is a
   separate card.
3. **Build vs runtime** -- "configure CI to upload" is a build
   card; "verify push token registration" is a runtime card.
4. **Write vs read** -- listing is one card; detail/edit is another.

## Anti-patterns

- **One card per week.** Way too big. Split.
- **No acceptance criterion.** Vague. Rewrite with the form
  "given X, when Y, then Z" or "exhibits N frames per second" or
  "uploads to TestFlight in CI".
- **No verification method.** If you cannot describe how to prove
  it works, the card is not yet well-defined.
- **DAG with cycles.** Means two cards depend on each other;
  usually one of them is wrong. Add an intermediate card.
- **No dependency edges.** Means every card is parallel; usually
  wrong -- there is always a sequencing.
