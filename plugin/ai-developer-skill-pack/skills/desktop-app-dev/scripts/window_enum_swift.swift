// Swift on Windows: top-level window enumeration with FindWindowW + EnumWindows.
//
// The koffi FFI does not support raw stdcall callbacks on Windows. We
// therefore call user32 directly via WinSDK bindings. The EnumWindows
// callback runs in a background thread guarded by a 3-second timeout.

import Foundation
import WinSDK

public struct WindowInfo: Sendable, Hashable {
    public let hwnd: Int64
    public let title: String
    public let className: String
}

public final class WindowFinder: @unchecked Sendable {
    public static let `default` = WindowFinder()

    private let lock = NSLock()
    private var cache: [String: Int64] = [:]
    public var timeoutSeconds: Double = 3.0

    public init() {}

    public func find(className: String?, titleSubstring: String) -> Int64? {
        let key = "\(className ?? "")|\(titleSubstring)"
        lock.lock(); defer { lock.unlock() }
        if let hwnd = cache[key], isWindow(hwnd) { return hwnd }
        cache.removeValue(forKey: key)
        if let cls = className, !hasWildcards(titleSubstring) {
            let hwnd = withCString(cls) { clsPtr -> HWND? in
                withCString(titleSubstring) { titlePtr -> HWND? in
                    FindWindowW(clsPtr, titlePtr)
                }
            }
            if let h = hwnd, h != nil, h?.value != 0 {
                cache[key] = Int64(h!.value)
                return Int64(h!.value)
            }
        }
        let results = enumWithTimeout(className: className, titleSubstring: titleSubstring, matchAll: false)
        if let first = results.first {
            cache[key] = first.hwnd
            return first.hwnd
        }
        return nil
    }

    public func listWindows(className: String? = nil) -> [WindowInfo] {
        enumWithTimeout(className: className, titleSubstring: "", matchAll: true)
    }

    public func invalidate() {
        lock.lock(); cache.removeAll(); lock.unlock()
    }

    // ---- Internals ---------------------------------------------------------

    private func isWindow(_ hwnd: Int64) -> Bool {
        var r: Bool = false
        r = IsWindow(HWND(bound: hwnd)) != 0
        return r
    }

    private func hasWildcards(_ s: String) -> Bool {
        s.contains("*") || s.contains("?")
    }

    private func enumWithTimeout(className: String?, titleSubstring: String, matchAll: Bool) -> [WindowInfo] {
        var results: [WindowInfo] = []
        let resultsLock = NSLock()           // protects `results`
        let timeout = timeoutSeconds
        let holder = Holder { () -> Void in /* filled below */ }

        let callback: WNDENUMPROC = { hwnd, _ in
            // Lock-protected snapshot read so the main thread's cancel()
            // is observed by this worker-thread callback.
            if holder.snapshot { return false }
            let length = Int(GetWindowTextLengthW(hwnd))
            if length <= 0 && !matchAll { return true }
            var titleBuf = [UInt16](repeating: 0, count: length + 1)
            _ = GetWindowTextW(hwnd, &titleBuf, Int32(length + 1))
            let title = String(utf16CodeUnits: titleBuf, count: length)
            var clsBuf = [UInt16](repeating: 0, count: 256)
            _ = GetClassNameW(hwnd, &clsBuf, 256)
            let clsLen = clsBuf.firstIndex(of: 0) ?? clsBuf.count
            let cls = String(utf16CodeUnits: clsBuf, count: clsLen)
            if let want = className, cls != want { return true }
            if !matchAll && !titleSubstring.isEmpty && !title.contains(titleSubstring) { return true }
            resultsLock.lock()
            results.append(WindowInfo(hwnd: Int64(hwnd.value), title: title, className: cls))
            resultsLock.unlock()
            return true
        }

        // Assign body after `callback` and `holder` are defined so the
        // closure captures them.
        holder.body = { _ = EnumWindows(callback, LPARAM(0)) }

        let thread = Thread(block: holder.body)
        thread.start()
        let deadline = Date().addingTimeInterval(timeout)
        while thread.isExecuting && Date() < deadline {
            Thread.sleep(forTimeInterval: 0.05)
        }
        if thread.isExecuting {
            holder.cancel()
            let deadline2 = Date().addingTimeInterval(0.1)
            while thread.isExecuting && Date() < deadline2 {
                Thread.sleep(forTimeInterval: 0.01)
            }
        }
        resultsLock.lock()
        let snapshot = results
        resultsLock.unlock()
        return snapshot
    }

    private final class Holder {
        var body: () -> Void
        private let lock = NSLock()
        private var _cancel: Bool = false
        init(_ body: @escaping () -> Void) { self.body = body }
        func cancel() { lock.lock(); _cancel = true; lock.unlock() }
        // Lock-protected snapshot read for cross-thread EnumWindows callback.
        var snapshot: Bool { lock.lock(); defer { lock.unlock() }; return _cancel }
    }
}


