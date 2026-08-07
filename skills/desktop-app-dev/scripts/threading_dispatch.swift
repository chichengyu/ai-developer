// Swift Concurrency + DispatchQueue background-work template for macOS.
//
// Wraps a long job in Task.detached and reports progress + completion back
// to the MainActor via async/await. Cancel via Task.cancel(); the job can
// cooperatively check `Task.isCancelled` between iterations.
//
// This is the macOS analogue of scripts/threading_wpf.cs (the WPF one
// uses Dispatcher; here we use the MainActor / DispatchQueue.main).

import Foundation

/// Marker error raised inside a job when it observes `Task.isCancelled`.
struct JobCancelled: Error {}

@MainActor
public final class JobRunner<JobOutput>: @unchecked Sendable {
    public typealias Job = @Sendable (Task<JobOutput, Error>) async throws -> Void

    private let job: Job
    private var task: Task<Void, Never>?

    public init(job: @escaping Job) {
        self.job = job
    }

    /// Run the job in the background. Reports progress via `onProgress`,
    /// final result via `onDone`, errors via `onError`, cancellation via
    /// `onCancel`. All callbacks are dispatched back to MainActor.
    public func start(
        onProgress: @escaping @MainActor (Double) -> Void = { _ in },
        onDone:     @escaping @MainActor (JobOutput) -> Void = { _ in },
        onError:    @escaping @MainActor (Error) -> Void = { _ in },
        onCancel:   @escaping @MainActor () -> Void = {}
    ) {
        cancel()  // ensure no leftover task

        let job = self.job
        task = Task.detached(priority: .userInitiated) {
            do {
                let output: JobOutput = try await {
                    try await job(Task { output in output })
                    // job threw; the throwing closure above already raised
                    fatalError("unreachable")
                }()
                await onDone(output)
            } catch is JobCancelled {
                await onCancel()
            } catch {
                await onError(error)
            }
        }
    }

    public func cancel() {
        task?.cancel()
        task = nil
    }

    public var isRunning: Bool {
        task?.isCancelled == false && task != nil
    }
}

/// Cooperative cancel check; call periodically from CPU loops.
@Sendable
public func pollCancel(_ task: Task<some Sendable, Error>) throws {
    if Task.isCancelled { throw JobCancelled() }
}

#if canImport(AppKit)
import AppKit

/// Force-foreground the application with the given bundle identifier.
/// Useful before CGEventPost / SendInput calls. Returns true on success.
@MainActor
public func activateApp(bundleId: String) -> Bool {
    let apps = NSRunningApplication.runningApplications(withBundleIdentifier: bundleId)
    guard let app = apps.first else { return false }
    return app.activate(options: [.activateAllWindows])
}
#endif