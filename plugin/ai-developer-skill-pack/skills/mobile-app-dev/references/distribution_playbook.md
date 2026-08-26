# Distribution playbook

Per-framework packaging, signing, Fastlane lanes, and CI snippets.
Read this when Step 5 needs concrete commands and when Step 6's
"uploads successfully" checkbox is being met.

---

## iOS (Swift / SwiftUI / UIKit / Flutter-iOS / RN-iOS / MAUI-iOS)

### Tooling

- Xcode 15+ on macOS 14+
- `xcodebuild` CLI (full Xcode, not just CLT)
- `xcrun altool` (deprecated for upload; prefer `xcrun notarytool` +
  `xcrun altool --upload-app` OR `fastlane pilot upload`)
- Fastlane (`brew install fastlane`)

### Build / archive

```bash
# Clean
xcodebuild clean -workspace MyApp.xcworkspace -scheme MyApp -configuration Release

# Archive
xcodebuild archive \
  -workspace MyApp.xcworkspace \
  -scheme MyApp \
  -configuration Release \
  -destination "generic/platform=iOS" \
  -archivePath build/MyApp.xcarchive \
  CODE_SIGNING_REQUIRED=NO \
  CODE_SIGNING_ALLOWED=NO

# Export
xcodebuild -exportArchive \
  -archivePath build/MyApp.xcarchive \
  -exportPath build/ipa \
  -exportOptionsPlist ExportOptions.plist
```

Or just `scripts/build_swift_ios.ps1 -Configuration Release -Arch arm64`.

### ExportOptions.plist

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>method</key>            <string>app-store</string>
    <key>uploadSymbols</key>     <true/>
    <key>uploadBitcode</key>     <false/>
    <key>teamID</key>            <string>YOUR_TEAM_ID</string>
    <key>signingStyle</key>      <string>manual</string>
</dict>
</plist>
```

### Upload to App Store Connect

```bash
# Option A: altool (works, deprecated)
xcrun altool --upload-app -f build/ipa/MyApp.ipa -t ios -u $APPLE_ID -p $APP_SPECIFIC_PWD

# Option B: Fastlane pilot
fastlane pilot upload --ipa build/ipa/MyApp.ipa

# Option C: Transporter (GUI)
open -a Transporter
```

### Upload to TestFlight

```bash
fastlane pilot upload --ipa build/ipa/MyApp.ipa --skip_submission true
# Then manually add testers via App Store Connect -> TestFlight
```

### Phased release

```ruby
# Fastfile
lane :release do
  deliver(
    submit_for_review: true,
    automatic_release: false,
    phased_release: true,
    precheck_include_in_app_purchases: false
  )
end
```

### Code signing

Xcode automatic signing (good for solo / small team):

```bash
xcodebuild -resolvePackageDependencies
xcodebuild -scheme MyApp -destination "generic/platform=iOS" -configuration Release \
  DEVELOPMENT_TEAM=YOUR_TEAM_ID \
  CODE_SIGN_STYLE=Automatic
```

Fastlane match (good for CI / larger team):

```bash
fastlane match development    --git_url git@github.com:org/certs.git
fastlane match adhoc          --git_url git@github.com:org/certs.git
fastlane match appstore       --git_url git@github.com:org/certs.git
```

See `references/signing_certificates.md` for cert types and rotation.

---

## Android (Kotlin / Compose / Flutter-Android / RN-Android / MAUI-Android)

### Tooling

- JDK 17 (Temurin recommended)
- Android SDK + build-tools 34+
- Gradle 8+ (Gradle wrapper handles this)
- `bundletool` for APK set generation (`brew install bundletool`)

### Build

```bash
# Universal APK (sideload)
gradle :app:assembleRelease

# AAB (Play Store)
gradle :app:bundleRelease

# APK set from AAB (for Play internal track sideload)
bundletool build-apks --bundle=app-release.aab --output=app-release.apks \
  --connected-device --ks=keystore.jks --ks-pass=pass:...
```

Or `scripts/build_kotlin_android.ps1 -Flavor production`.

### Signing

Two-layer model (recommended):

1. **Upload key** -- yours, in `~/.keystores/upload.jks`. Used to sign
   the AAB you upload.
2. **App signing key** -- Google's, used to sign the final APK that
   users install. Generated automatically when you enroll in Play
   App Signing.

```bash
# Generate upload keystore (do once)
keytool -genkey -v -keystore upload.jks -keyalg RSA -keysize 2048 \
  -validity 10000 -alias upload

# Write key.properties (gitignored)
cat > key.properties <<EOF
storeFile=upload.jks
storePassword=...
keyAlias=upload
keyPassword=...
EOF
```

In `app/build.gradle.kts`:

```kotlin
val keystoreProperties = Properties().apply {
    load(rootProject.file("key.properties").inputStream())
}

android {
    signingConfigs {
        create("release") {
            keyAlias = keystoreProperties["keyAlias"] as String
            keyPassword = keystoreProperties["keyPassword"] as String
            storeFile = file(keystoreProperties["storeFile"] as String)
            storePassword = keystoreProperties["storePassword"] as String
        }
    }
    buildTypes {
        release {
            signingConfig = signingConfigs.getByName("release")
            isMinifyEnabled = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }
}
```

### Upload to Play Console

```bash
# Option A: Gradle Play Publisher plugin
gradle publishRelease

# Option B: Fastlane supply
fastlane supply --aab app-release.aab --track internal --json_key api-key.json

# Option C: Manual via Play Console web UI
```

### Staged rollout

```ruby
# Fastfile
lane :release do
  upload_to_play_store(
    track: 'production',
    rollout: '0.1',   # 10% per day for 7 days
    aab: 'app-release.aab',
    json_key: 'api-key.json'
  )
end

lane :halt do
  upload_to_play_store(
    track: 'production',
    rollout: '0',     # halt rollout
    version_code: ENV['VERSION_CODE']
  )
end
```

---

## Flutter

### iOS

```bash
flutter build ipa --release --export-options-plist=ios/ExportOptions.plist
flutter build ios --release --no-codesign   # for archive-only
```

Or `scripts/build_flutter.ps1 -Platform ios`.

### Android

```bash
flutter build appbundle --release
flutter build apk --release --split-per-abi
```

Or `scripts/build_flutter.ps1 -Platform android`.

### Code signing

Flutter reads the same `ios/ExportOptions.plist` for iOS and the same
`key.properties` + Gradle config for Android. No special Flutter-only
signing step.

---

## React Native (bare workflow)

### iOS

```bash
cd ios && pod install && cd ..
npx react-native build-ios --mode Release
```

### Android

```bash
cd android && ./gradlew :app:bundleRelease && cd ..
```

Or `scripts/build_react_native.ps1`.

### Expo

```bash
# eas.json must have a build profile
eas build --platform ios --profile production
eas build --platform android --profile production
eas submit --platform ios --latest
eas submit --platform android --latest
```

---

## .NET MAUI

### iOS

```bash
dotnet publish -f net8.0-ios -c Release -p:RuntimeIdentifier=ios-arm64
```

### Android

```bash
dotnet publish -f net8.0-android -c Release -p:RuntimeIdentifier=android-arm64
```

Or `scripts/build_dotnet_maui.ps1 -Platform ios|android`.

---

## Kotlin Multiplatform

### iOS

```bash
xcodebuild -workspace MyApp.xcworkspace -scheme MyApp -configuration Release \
  -destination "generic/platform=iOS" archive
```

### Android

```bash
gradle :composeApp:assembleRelease
```

Or `scripts/build_kmp.ps1`.

---

## Fastlane Fastfile skeleton

Place this in the project root as `Fastfile`:

```ruby
default_platform(:ios)

APP_ID      = "com.example.myapp"
BUNDLE_ID   = "com.example.myapp"
TEAM_ID     = "ABCDE12345"
APPLE_ID    = "you@example.com"

platform :ios do
  desc "Run all iOS tests"
  lane :test do
    run_tests(
      workspace: "MyApp.xcworkspace",
      scheme: "MyApp",
      device: "iPhone 14",
      clean: true
    )
  end

  desc "Push to TestFlight"
  lane :beta do
    build_app(
      workspace: "MyApp.xcworkspace",
      scheme: "MyApp",
      export_method: "app-store",
      output_directory: "./build"
    )
    upload_to_testflight(
      skip_waiting_for_build_processing: true,
      apple_id: APPLE_ID
    )
  end

  desc "Release to App Store"
  lane :release do
    build_app(
      workspace: "MyApp.xcworkspace",
      scheme: "MyApp",
      export_method: "app-store"
    )
    upload_to_app_store(
      force: true,
      reject_if_possible: true,
      automatic_release: false,
      phased_release: true,
      precheck_include_in_app_purchases: false,
      submission_information: {
        add_id_info_uses_idfa: false
      }
    )
  end

  desc "Promote latest TestFlight build to production"
  lane :promote do
    deliver(
      precheck_include_in_app_purchases: false,
      automatic_release: false,
      phased_release: true
    )
  end
end

platform :android do
  desc "Run all Android tests"
  lane :test do
    gradle(task: "test", project_dir: "android/")
  end

  desc "Push to Play internal track"
  lane :beta do
    gradle(
      task: "bundleRelease",
      project_dir: "android/",
      properties: { "android.injected.signing.store.file" => ENV["KEYSTORE_PATH"] }
    )
    upload_to_play_store(
      track: "internal",
      json_key: ENV["GOOGLE_PLAY_JSON_KEY_PATH"],
      aab: "android/app/build/outputs/bundle/release/app-release.aab"
    )
  end

  desc "Release to Play production"
  lane :release do
    gradle(task: "bundleRelease", project_dir: "android/")
    upload_to_play_store(
      track: "production",
      rollout: "0.1",
      json_key: ENV["GOOGLE_PLAY_JSON_KEY_PATH"],
      aab: "android/app/build/outputs/bundle/release/app-release.aab"
    )
  end

  desc "Halt rollout"
  lane :halt do
    upload_to_play_store(
      track: "production",
      rollout: "0",
      json_key: ENV["GOOGLE_PLAY_JSON_KEY_PATH"]
    )
  end
end
```

Install:

```bash
bundle install
bundle exec fastlane ios beta
bundle exec fastlane android release
```

---

## CI snippets

### GitHub Actions: iOS + Android

```yaml
name: Build
on: [push]
jobs:
  ios:
    runs-on: macos-14
    steps:
      - uses: actions/checkout@v4
      - uses: subosito/flutter-action@v2
      - run: flutter pub get
      - run: cd ios && pod install && cd ..
      - run: flutter build ipa --release --export-options-plist=ios/ExportOptions.plist
      - uses: apple-actions/upload-testflight-build@v3
        with:
          app-store-connect-api-key: ${{ secrets.ASC_API_KEY }}
          ipa-path: build/ios/ipa/MyApp.ipa

  android:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with: { distribution: temurin, java-version: 17 }
      - uses: subosito/flutter-action@v2
      - run: flutter pub get
      - run: flutter build appbundle --release
      - uses: r0adkll/upload-google-play@v1
        with:
          serviceAccountJsonPlainText: ${{ secrets.GOOGLE_PLAY_JSON_KEY }}
          packageName: com.example.myapp
          releaseFiles: build/app/outputs/bundle/release/app-release.aab
          track: internal
```
