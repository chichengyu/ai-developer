# Security hardening

Apply these controls before shipping, especially for finance, health,
enterprise, and anything handling user-generated content.

## Secrets and credentials

- Never commit signing keys, `.p12`, `.p8`, `.jks`, `.mobileprovision`,
  `key.properties`, `GoogleService-Info.plist`, or `google-services.json`.
- Inject API keys / tokens at build time or fetch them from a remote
  config service.
- Store user tokens in Keychain (iOS), EncryptedSharedPreferences /
  Keystore (Android), flutter_secure_storage / MMKV with encryption,
  or the platform equivalent.

## Network

- Enforce HTTPS; disable cleartext traffic on Android and
  `NSAllowsArbitraryLoads=false` on iOS.
- Pin certificates for critical API domains, but ship a rotation path
  to avoid outage when the cert changes.
- Add certificate transparency / public-key pinning only when the
  backend team supports it.

## Device attestation

- iOS: App Attest for server-side integrity checks.
- Android: Play Integrity API; treat the verdict as a signal, not a
  guarantee.
- Do not gate the whole app on attestation; degrade gracefully when
  the device cannot attest.

## Jailbreak / root

- Detect only when it changes the threat model (banking, enterprise
  data at rest).
- Never use detection alone as the only control; combine with
  server-side risk signals.
- Avoid false positives that block legitimate users on modified
  devices.

## Data at rest

- Use platform encrypted storage for sensitive fields.
- Disable backup for auth/session files if required by the threat
  model (`allowBackup=false`, `excludeFromBackup`).
- Encrypt local databases with SQLCipher or platform keychain-backed
  encryption when the app stores PII.

## Privacy and compliance

- Keep privacy nutrition labels and the Play data safety form in sync
  with the SDK list.
- Collect only what Step 0 documents; add an SDK inventory in the
  repo.
- Provide account deletion and data export when required.

## Release checklist

- [ ] No debug logging, `print()`, `NSLog()`, or `Log.d()` in release.
- [ ] No hardcoded secrets in source or binary assets.
- [ ] HTTPS-only, cleartext disabled.
- [ ] Keychain / Keystore used for tokens.
- [ ] Backup exclusions applied for sensitive files.
- [ ] Attestation / integrity integrated with graceful degradation.
- [ ] Privacy labels and data safety form match actual SDKs.
