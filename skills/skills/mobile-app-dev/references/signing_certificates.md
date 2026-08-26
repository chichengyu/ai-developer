# Signing and certificates

Everything you need to know to keep your iOS and Android signing material
correct, secure, and reproducible. Read this in full before the first
production build; skim on later builds.

---

## iOS

### Account types

| Account             | Cost      | Allows                          |
|---------------------|-----------|----------------------------------|
| Apple ID (free)     | free      | Simulator + device development on your own devices only. No TestFlight, no App Store. |
| Apple Developer Program | $99 / yr | Full: device install on any device, TestFlight, App Store, App Store Connect API. |
| Apple Developer Enterprise Program | $299 / yr | Ad-hoc distribution to internal employees only. Cannot publish to App Store. |

For any app that ships to other people, you need the $99/yr program.

### Cert types

| Cert                             | Lifetime | Purpose |
|----------------------------------|----------|---------|
| Apple Development                | 1 year   | Build that runs on your registered device list. |
| Apple Distribution               | 1 year   | Build for TestFlight + App Store. |
| Apple Ad Hoc                     | 1 year   | Same as Distribution but only to your ad-hoc device list (no TestFlight). |
| Apple Worldwide Developer Relations | -- | Only for push notification server-side cert (separate flow). |

### Provisioning profiles

A provisioning profile ties together:

- An app ID (e.g., `com.example.myapp`)
- A list of allowed devices (for development / ad-hoc) or no restriction (for app-store)
- A signing cert
- Entitlements (capabilities like Push, App Groups, Keychain Sharing)

Three types:

- **Development** -- your device list, your development cert.
- **Ad Hoc** -- your device list, your distribution cert. Limited to 100 devices per year per device type.
- **App Store** -- no device restriction, distribution cert.

### Where the files live

| File                         | Where                                               | Backup |
|------------------------------|------------------------------------------------------|--------|
| `.p12` cert + private key    | `~/Library/Developer/Xcode/UserData/.../Certificates/`, exported manually, or in `match` repo | Bitwarden / 1Password / encrypted Git repo via `match`. |
| `.mobileprovision` profiles  | `~/Library/MobileDevice/Provisioning Profiles/`      | `match` repo |
| `developerprofile.*`         | Xcode-managed `xcodebuild -exportArchive` consumes these | `match` repo |

### Manual vs Automatic signing

**Automatic signing** (Xcode-managed):

- Xcode creates a development cert, profile, and registers your device
  on first use.
- Pros: zero config for solo work.
- Cons: not reproducible; CI must call `xcodebuild` with the right
  team ID and let Xcode talk to Apple.

**Manual signing** (cert + profile files in repo or `match`):

- Pros: reproducible builds; CI works without interactive sign-in.
- Cons: you must manage rotation manually.

### Fastlane match (recommended for any team >= 2)

```bash
# One-time
fastlane match init --git_url git@github.com:org/certs-repo.git

# Per cert type
fastlane match development
fastlane match adhoc
fastlane match appstore
```

`match` creates:

- `.p12` certs and private keys, stored in the certs repo.
- `.mobileprovision` profiles in `~/Library/MobileDevice/Provisioning Profiles/`.
- The certs repo is the **single source of truth** -- never commit
  `.p12` files outside it.

### CI signing

GitHub Actions:

```yaml
- uses: apple-actions/import-codesigncert@v3
  with:
    p12-file-base64: ${{ secrets.CERT_P12_BASE64 }}
    p12-password: ${{ secrets.CERT_P12_PASSWORD }}

- uses: apple-actions/download-provisioning-profiles@v2
  with:
    bundle-id: com.example.myapp
    profile-type: APP_STORE
    issuer-id: ${{ secrets.ASC_ISSUER_ID }}
    api-key-id: ${{ secrets.ASC_KEY_ID }}
    api-private-key: ${{ secrets.ASC_API_KEY }}
```

Bitrise:

- Use the **Certificate and Profile Installer** step (or **Manage iOS
  Code Signing** step) to install `match` output.
- Use **Deploy to App Store Connect** step to upload.

### App Store Connect API key (for CI upload)

1. App Store Connect -> Users and Access -> Keys -> App Store Connect API -> Generate.
2. Save `.p8` file, Issuer ID, Key ID.
3. In CI: `xcrun altool --upload-app -f MyApp.ipa -t ios --apiKey <KEY_ID> --apiIssuer <ISSUER_ID>`.
4. Or pass to Fastlane via `app_store_connect_api_key`.

### Token rotation

Certs last 1 year. Plan to renew 2-4 weeks before expiry:

- `fastlane match renew_development`
- `fastlane match renew_distribution`

Push the certs repo with the renewed certs.

### Common errors

| Error                                   | Cause | Fix |
|-----------------------------------------|-------|-----|
| `No signing identity "iPhone Developer"` | Expired cert | `match` again |
| `Provisioning profile ... expired`       | Expired profile | `match` again |
| `Code signing is required for product type 'Application'` | Manual signing set up but no cert | Set `CODE_SIGNING_REQUIRED=NO` for simulator builds, or install cert. |
| `Your build settings specify a provisioning profile ... however no provisioning profile matching the entitlements` | Wrong profile for entitlements (e.g., Push entitlement but no push profile) | Generate a profile with the right entitlements via Apple Developer portal. |
| `App Store Connect Operation Error: ... is already in use` | Bundle ID conflict | Change bundle ID, or take over an orphan ID via Apple Support. |

---

## Android

### Two-key model

- **Upload key** -- yours, in `~/.keystores/upload.jks`. Used to sign
  the AAB you upload to Play Console.
- **App signing key** -- Google's, used to sign the APK users install.
  Generated when you enroll in Play App Signing.

When you renew the upload key, you must also tell Google via
**Setup -> App Integrity -> Request upload key reset**. There is a
30-day grace period.

### Generate upload keystore (do once, keep forever)

```bash
keytool -genkey -v \
  -keystore ~/.keystores/upload.jks \
  -keyalg RSA -keysize 2048 \
  -validity 10000 \
  -alias upload \
  -storepass <store-password> \
  -keypass <key-password> \
  -dname "CN=Upload Key, OU=Engineering, O=MyApp, L=City, S=State, C=US"
```

**Never commit `upload.jks` to git.** Use environment variables or a
secrets manager.

### Key rotation

- Lost key: use Google's "Request upload key reset" workflow.
- Compromised key: same, with "compromised" as the reason.
- Routine rotation: not recommended unless necessary; the 10000-day
  validity means it rarely needs it.

### Play App Signing enrollment

1. Play Console -> Setup -> App integrity -> App signing.
2. Choose "Use Google-generated key" (default) OR "Use my own key"
   (bring your own).
3. After enrollment, Google generates the app signing key. You only
   ever deal with the upload key.

### Play Integrity API

For backend APIs that want to verify requests come from a genuine
Play-distributed binary:

1. Play Console -> Setup -> Play Integrity API.
2. Link a Google Cloud project.
3. In your backend, call the Play Integrity REST API to decode the
   verdict token.

### API key for CI upload

1. Google Cloud Console -> IAM -> Service Accounts -> Create.
2. Grant "Service Account User" + "Play Store Release Manager" (or
   custom role with `releases.create`).
3. Create JSON key, save as `play-api-key.json` (gitignored).
4. In CI: pass as secret, reference in Fastlane as `json_key`.

### Common errors

| Error                                   | Cause | Fix |
|-----------------------------------------|-------|-----|
| `Keystore was tampered with, or password was incorrect` | Wrong `keyPassword` | Check `key.properties` and Gradle config. |
| `You uploaded an APK or Android App Bundle that was signed in debug mode` | Signed with debug key | Re-build with release signing config. |
| `Your app currently targets API level ... which is below the minimum required level` | Old `targetSdk` | Bump to the current Play Console minimum; the requirement rises every year. |
| `Play Integrity API: failed to fetch the app attestation verdict` | Missing SHA-256 fingerprint in Play Console | Add the SHA-256 of the upload key to Play Console. |

---

## Cross-platform signing quirks

### Flutter

- iOS: same `ios/ExportOptions.plist` and `match`-managed certs.
- Android: same `android/key.properties` and Gradle config.

### React Native (bare)

- iOS: same Xcode workspace as native iOS.
- Android: same Gradle config as native Android.

### .NET MAUI

- iOS: `dotnet publish -f net8.0-ios ...` calls `xcodebuild` under
  the hood, so `match`-managed certs work.
- Android: `dotnet publish -f net8.0-android ...` calls Gradle; the
  same `key.properties` works.

### Kotlin Multiplatform

- iOS app target uses Xcode-managed signing.
- Android uses standard Gradle signing.

### Capacitor

- iOS: standard Xcode signing.
- Android: standard Gradle signing.
- Note: Capacitor apps are WebView-rendered; App Store reviewers
  sometimes reject for "no useful native functionality" if the
  WebView URL is just your existing website.

---

## What to never commit

Add to `.gitignore` immediately:

```
*.p12
*.p8
*.jks
*.keystore
*.mobileprovision
key.properties
google-services.json
GoogleService-Info.plist
```

If any of these have been committed historically:

1. Rotate the credential immediately (revoke cert, mint new keystore).
2. Purge with `git filter-repo --invert-paths --path <file>`.
3. Force push; tell the team to re-clone.
