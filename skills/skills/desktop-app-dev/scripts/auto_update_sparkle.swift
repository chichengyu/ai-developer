// auto_update_sparkle.swift -- Sparkle 2.x auto-update framework integration.
//
// Sparkle (https://sparkle-project.org/) is the de-facto macOS auto-update
// framework. Drop SPUUpdater into your AppDelegate / SwiftUI app; serve
// an `appcast.xml` over HTTPS; users get updates with code-signed diffs.
//
// Install:
//   1. Add Sparkle via SPM: https://github.com/sparkle-project/Sparkle
//   2. Link Sparkle.framework; copy Sparkle.framework into your .app bundle.
//
// Build the appcast with the `generate_appcast` tool shipped with Sparkle.
//
// Reference: https://sparkle-project.org/documentation/

import Foundation
import Sparkle

/// Wraps SPUUpdater with sane defaults. Use one instance per app, lifetime
/// tied to the app's main run loop.
public final class Updater: NSObject, SPUUpdaterDelegate {
    public static let shared = Updater()

    private let updater: SPUUpdater

    public override init() {
        // The host bundle is the running .app.
        let hostBundle = Bundle.main
        // The driver listens to user actions (Check for Updates menu item).
        let driver = SPUStandardUserDriver(hostBundle: hostBundle, delegate: nil)
        self.updater = SPUUpdater(hostBundle: hostBundle,
                                  applicationBundle: hostBundle,
                                  userDriver: driver,
                                  delegate: nil)
        super.init()
        self.updater.delegate = self
    }

    /// Start the updater. Checks the feed once at launch (configurable)
    /// and then on demand.
    public func start(feedURL: URL) {
        updater.setFeedURL(feedURL)
        updater.start()
    }

    /// Trigger an explicit "Check for Updates..." action.
    public func checkForUpdates() {
        updater.checkForUpdates()
    }

    /// Allow checking for updates without showing UI.
    public func checkInBackground() {
        updater.checkForUpdatesInBackground()
    }

    // ---- SPUUpdaterDelegate ----------------------------------------------
    public func updater(_ updater: SPUUpdater, mayPerformCheckForUpdates check: SPUUpdaterCheck) -> Bool {
        // Return false to suppress checking (e.g. when offline).
        return true
    }

    public func feedURLString(for updater: SPUUpdater) -> String? {
        // Return the feed URL string for telemetry / logs.
        return updater.feedURL?.absoluteString
    }
}

// ---- SwiftUI integration sketch -------------------------------------------
// 1. Call Updater.shared.start(feedURL: URL(string: "https://updates.example.com/myapp/appcast.xml")!)
//    from your App.init() or SceneDelegate.
// 2. Add a "Check for Updates..." menu item in your main MenuBar:
//    Button("Check for Updates...") { Updater.shared.checkForUpdates() }
//       .keyboardShortcut("u", modifiers: .command)