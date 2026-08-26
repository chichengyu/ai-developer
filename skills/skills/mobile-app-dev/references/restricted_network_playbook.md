# Restricted network playbook

Build iOS and Android apps when you cannot reach the public internet
from the build host, or when the developer network is firewalled.
Read this if your environment blocks `pub.dev`, `registry.npmjs.org`,
`dl.google.com`, or `services.gradle.org`.

---

## What "restricted network" means

A Windows or Linux build host that:

- Cannot resolve DNS for `github.com`, `pub.dev`, `npmjs.com`.
- Cannot reach `dl.google.com` (Android SDK / Maven Central mirror).
- Has no write access to the host filesystem outside the project root.
- Has no `pip install` or `brew install` available without escalation.

This is the default in many enterprise / state environments. It is
also the case when the Codex app runs in a sandboxed shell.

## Strategies

### 1. Vendor (preferred for production)

Mirror every dependency into the project once, on a host with internet,
then ship the vendored tree with the source.

#### CocoaPods

```bash
# On a host with internet:
pod install --no-repo-update
# Then tarball the Pods/ directory and Podfile.lock
tar -czf pods-vendored.tar.gz Pods/ Podfile.lock

# On the restricted host:
tar -xzf pods-vendored.tar.gz
pod install --no-repo-update
```

Or use `:path => 'VendoredPods/MyLib.podspec'` in the Podfile.

#### Swift Package Manager

```bash
# In Package.swift
.package(path: "VendoredPackages/MyLib")

# Build on restricted host:
swift build --offline
```

#### Gradle

```bash
# On a host with internet, configure a local cache:
echo "org.gradle.caching=true" >> gradle.properties

# Pre-warm:
./gradlew --refresh-dependencies :app:assembleRelease

# Tarball ~/.gradle/caches/ and ship with the project:
tar -czf gradle-cache.tar.gz -C ~/.gradle caches/

# On the restricted host:
tar -xzf gradle-cache.tar.gz -C ~/.gradle
./gradlew --offline :app:assembleRelease
```

#### pub (Flutter / Dart)

```bash
# On a host with internet, prime the cache:
flutter pub get
tar -czf pub-cache.tar.gz -C ~/.pub-cache .

# On the restricted host:
tar -xzf pub-cache.tar.gz -C ~/.pub-cache
PUB_CACHE=~/.pub-cache flutter pub get --offline
```

#### npm / yarn (React Native)

```bash
# Vendoring
npm install
tar -czf node-modules.tar.gz node_modules package-lock.json

# On the restricted host:
tar -xzf node-modules.tar.gz
npm ci --offline
```

#### .NET MAUI

```bash
# On a host with internet, prime the NuGet cache:
dotnet restore
# NuGet cache lives at ~/.nuget/packages

# Ship the cache:
tar -czf nuget-cache.tar.gz -C ~/.nuget packages/

# On the restricted host:
tar -xzf nuget-cache.tar.gz -C ~/.nuget
dotnet restore --offline
```

### 2. Configure an internal mirror

Many enterprises have an internal Nexus / Artifactory / Verdaccio:

- **Maven Central / Google Maven mirror**: `https://nexus.corp/repository/maven-public/`
- **CocoaPods specs mirror**: `https://nexus.corp/repository/cocoapods-public/`
- **npm registry mirror**: `https://nexus.corp/repository/npm-public/`
- **pub.dev mirror**: `https://pub.corp/`
- **NuGet feed**: `https://nexus.corp/repository/nuget-public/`

Configure via:

#### Gradle (`~/.gradle/init.gradle.kts`)

```kotlin
allprojects {
    repositories {
        maven { url = uri("https://nexus.corp/repository/maven-public/") }
        mavenCentral()  // fallback; only used if mirror misses
        google()
    }
}
```

#### CocoaPods (`~/.cocoapods/config.yaml` or in Podfile)

```ruby
source 'https://nexus.corp/repository/cocoapods-public/'
```

#### npm (`~/.npmrc`)

```
registry=https://nexus.corp/repository/npm-public/
```

#### pub (`PUB_HOSTED_URL`)

```bash
export PUB_HOSTED_URL=https://pub.corp
export FLUTTER_STORAGE_BASE_URL=https://storage.flutter.corp
flutter pub get
```

#### NuGet (`~/.nuget/NuGet/NuGet.Config`)

```xml
<configuration>
    <packageSources>
        <clear />
        <add key="corp" value="https://nexus.corp/repository/nuget-public/" />
    </packageSources>
</configuration>
```

### 3. Pre-built SDK / NDK / toolchain

For Android: the Android SDK and NDK can be installed once and
shipped:

```bash
# Download on internet host
sdkmanager "platforms;android-34" "build-tools;34.0.0" \
    "platform-tools" "ndk;26.1.10909125"

# Tarball
tar -czf android-sdk.tar.gz -C ~/Library/Android sdk/

# On restricted host
tar -xzf android-sdk.tar.gz -C ~/Library/Android
export ANDROID_HOME=~/Library/Android/sdk
```

For iOS: Xcode and the iOS SDK are macOS-only and must already be
installed on the build host. There is no "portable Xcode".

For Flutter: the Flutter SDK itself must be installed locally and
can be vendored:

```bash
tar -czf flutter-sdk.tar.gz -C ~/development flutter/
tar -xzf flutter-sdk.tar.gz -C ~/development
export PATH=$PATH:~/development/flutter/bin
```

### 4. Code-signing offline

If you can build but cannot upload to App Store Connect / Play
Console, build the archive / AAB locally and copy it to a host with
network access for upload.

Or use App Store Connect API key + offline `xcrun altool` (the tool
ships with Xcode, no extra download needed).

---

## What works and what doesn't in restricted environments

| Need                                | Vendored cache works? | Mirror works? |
|-------------------------------------|------------------------|----------------|
| `xcodebuild` + iOS SDK              | Yes (Xcode must be preinstalled on Mac) | Yes |
| `xcodebuild` + iOS SDK (from Windows) | NO -- iOS needs macOS | NO |
| `gradle :app:assembleRelease`       | Yes (cache) | Yes |
| `gradle` first-time download        | NO without mirror | Yes |
| `pod install`                       | Yes (Pods/ dir) | Yes |
| `flutter build ipa`                 | Yes (cache + SDK) | Yes |
| `flutter build appbundle`           | Yes (cache + SDK) | Yes |
| `npm install` (RN)                  | Yes (node_modules) | Yes |
| `dotnet publish -f net8.0-ios`      | Yes (NuGet cache) | Yes |
| `dotnet publish -f net8.0-android`  | Yes (NuGet cache) | Yes |
| App Store upload                    | NO | YES if API key is pre-staged |
| Play Console upload                 | NO | YES if API key is pre-staged |
| `xcrun notarytool`                  | NO (needs apple.com) | -- |

## Workflow for a real project

1. On the internet host, run the build once. Capture every download:
   - `Pods/`
   - `~/.gradle/caches/`
   - `node_modules/`
   - `~/.pub-cache/`
   - `~/.nuget/packages/`
   - `~/Library/Android/sdk/`
2. Tarball each. Keep versions pinned (Podfile.lock, package-lock.json,
   pubspec.lock, gradle.lockfile).
3. Move the tarballs to the restricted host.
4. Extract to the canonical paths.
5. Build with `--offline` flags everywhere.
6. For distribution: build the archive / AAB on the restricted host,
   copy to the internet host, run the Fastlane upload lane there.
   Or run the lane from a CI job with network access.

## Hidden gotchas

- **Gradle daemon caches** are per-user and per-Gradle-version. Cache
  directories change between Gradle 8.x -> 8.y.
- **CocoaPods specs repo** is a git checkout that updates over time.
  Run `pod install` once and freeze.
- **Pub packages** use the host hash; mirror must serve exact bytes.
- **Xcode DerivedData** caches the iOS SDK; cleanup can break offline
  builds.
- **NPM packages** with `postinstall` scripts may need network access
  during build (e.g., node-gyp for sharp). Pre-built binaries in
  `node_modules` usually work but RN + Hermes sometimes surprises.
