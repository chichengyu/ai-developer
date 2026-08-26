# Requirements checklist

Fill this in for **every** mobile app request before picking a framework.
Items marked **[critical]** block the workflow if unanswered; if you cannot
answer them, ask the user.

---

## 0. Project meta

- **App name**: __________________________________________
- **Bundle ID / Application ID**: __________________________________________
- **Owner / team**: __________________________________________
- **First ship target date**: __________________________________________

---

## 1. Functional

| Question | Answer |
|----------|--------|
| 1.1 What does the app do (1 paragraph)? | |
| 1.2 List every screen / tab / modal. | |
| 1.3 What user actions mutate state? | |
| 1.4 Read-only vs user-generated vs sync'd data? | |
| 1.5 Offline-first requirements? **[critical]** | yes / no / partial |

---

## 2. Non-functional

| Question | Answer | Default |
|----------|--------|---------|
| 2.1 Cold start budget | ms | 1500 ms |
| 2.2 Memory ceiling | MB | 150 MB |
| 2.3 Battery / radio budget | mAh/h, MB/h | push only, no polling |
| 2.4 Accessibility scope | Dynamic Type, VoiceOver, contrast | iOS 16+, Android 8+ |
| 2.5 Localization scope + RTL | en only / multi-locale | en only |
| 2.6 Dark mode / dynamic color / system fonts | yes / no | yes |

---

## 3. Distribution **[critical]**

| Question | Answer |
|----------|--------|
| 3.1 App Store public release? | yes / no |
| 3.2 Play Store public release? | yes / no |
| 3.3 TestFlight / internal track? | yes / no |
| 3.4 Enterprise MDM? | yes / no |
| 3.5 Sideload only / direct APK? | yes / no |

---

## 4. Integration

| Question | Answer |
|----------|--------|
| 4.1 Backend API surface | REST / GraphQL / gRPC, base URL |
| 4.2 Auth scheme | OAuth / OIDC / API key / session / none |
| 4.3 Required OS frameworks | push, location, camera, mic, BT, NFC, HealthKit, ARKit, CarPlay, etc. |
| 4.4 Required 3rd-party SDKs | analytics, ads, crash, payments, maps |
| 4.5 Minimum OS version | iOS X+ / Android API Y+ |
| 4.6 Min RAM | GB |
| 4.7 Required sensors | GPS, accelerometer, gyroscope, magnetometer, barometer |

---

## 5. Failure modes

| Question | Answer |
|----------|--------|
| 5.1 Offline behavior | read-only / queued / dead-end |
| 5.2 Permission denied behavior | graceful degrade / crash |
| 5.3 Deep link target missing | 404 page / fallback route |
| 5.4 OS kills app in background | state restored from `SavedStateHandle` / SwiftData |
| 5.5 Jailbroken / rooted device | sensitive data only / unsupported / fine |

---

## 6. Compliance **[critical for finance / health / kids]**

| Question | Answer |
|----------|--------|
| 6.1 App Store privacy nutrition labels drafted? | yes / no |
| 6.2 Play Store data safety form drafted? | yes / no |
| 6.3 GDPR / CCPA / PIPL requirements | data export, delete, consent |
| 6.4 COPPA / kids? | yes / no |
| 6.5 Export compliance / encryption | exempt / CCATS needed |

---

## 7. Ops

| Question | Answer |
|----------|--------|
| 7.1 Crash reporting backend | Crashlytics / Sentry / Bugsnag |
| 7.2 Analytics backend | Firebase / Amplitude / Mixpanel / self |
| 7.3 Feature flag / remote config | LaunchDarkly / Firebase RC / ConfigCat |
| 7.4 CI/CD lane | GitHub Actions / Bitrise / GitLab CI |
| 7.5 Version cadence | semver (major.minor.patch), store build number |
| 7.6 Rollback plan | phased release / staged rollout / kill switch |

---

## Classification

- [ ] A. Utility / tools
- [ ] B. Productivity / LOB
- [ ] C. Social / community
- [ ] D. Game / interactive (out of scope -- game engine)
- [ ] E. Media / content
- [ ] F. Finance / health
- [ ] G. System / shell
- [ ] H. IoT / hardware

## Showstopper assumptions

Capture the assumption that, if wrong, blocks the project:

- ___________________________________________
- ___________________________________________

## Out of scope for v1

- ___________________________________________
- ___________________________________________

## Team profile

- Primary languages: Swift / Kotlin / Dart / TypeScript / C# / other: ______
- Existing codebases: native iOS / native Android / React / Flutter / .NET / web: ______
- Hiring pipeline / budget for new languages: ______
- Native vs cross-platform preference (if any): ______
