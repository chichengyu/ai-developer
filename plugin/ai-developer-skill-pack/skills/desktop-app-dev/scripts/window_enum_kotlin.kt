/**
 * Kotlin/JVM window enumeration via JNA. FindWindowW first, EnumWindows fallback
 * in a thread guarded by a 3-second timeout.
 *
 * Build:
 *   dependencies { implementation("net.java.dev.jna:jna:5.14.0") }
 *
 * Usage:
 *   val finder = WindowFinder()
 *   val hwnd = finder.find(className = null, titleSubstring = "Notepad")
 */
package desktop

import com.sun.jna.Native
import com.sun.jna.Pointer
import com.sun.jna.platform.win32.User32
import com.sun.jna.platform.win32.WinDef
import com.sun.jna.platform.win32.WinUser
import com.sun.jna.win32.StdCallLibrary
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicBoolean

data class WindowInfo(val hwnd: Long, val title: String, val className: String)

class WindowFinder(private val timeoutSeconds: Double = 3.0) {

    data class Key(val className: String?, val titleSubstring: String)
    private val cache = ConcurrentHashMap<Key, Long>()

    fun find(className: String?, titleSubstring: String): Long? {
        val key = Key(className, titleSubstring)
        cache[key]?.takeIf { isWindow(it) }?.let { return it }
        cache.remove(key)

        if (className != null && !hasWildcards(titleSubstring)) {
            val hwnd = User32.INSTANCE.FindWindowW(className, titleSubstring)
            if (hwnd != null) {
                val raw = Pointer.nativeValue(hwnd.pointer)
                cache[key] = raw
                return raw
            }
        }
        val matches = enumWithTimeout(className, titleSubstring, matchAll = false)
        if (matches.isNotEmpty()) {
            cache[key] = matches.first().hwnd
            return matches.first().hwnd
        }
        return null
    }

    fun listWindows(className: String? = null): List<WindowInfo> =
        enumWithTimeout(className, "", matchAll = true)

    fun invalidate() = cache.clear()

    // ---- Internals ---------------------------------------------------------

    private fun isWindow(hwnd: Long): Boolean {
        if (hwnd == 0L) return false
        val p = Pointer.createConstant(hwnd)
        return User32.INSTANCE.IsWindow(WinDef.HWND(p))
    }

    private fun hasWildcards(s: String): Boolean = s.contains('*') || s.contains('?')

    private fun enumWithTimeout(className: String?, titleSubstring: String, matchAll: Boolean): List<WindowInfo> {
        val results = mutableListOf<WindowInfo>()
        val done = AtomicBoolean(false)
        val listLock = Any()

        val callback = WinUser.WNDENUMPROC { hwnd, _ ->
            if (done.get()) return@WNDENUMPROC false
            val length = User32.INSTANCE.GetWindowTextLengthW(hwnd)
            if (length <= 0 && !matchAll) return@WNDENUMPROC true
            val titleBuf = CharArray(length + 1)
            User32.INSTANCE.GetWindowTextW(hwnd, titleBuf, length + 1)
            val title = String(titleBuf).trimEnd('\u0000')
            val clsBuf = CharArray(256)
            User32.INSTANCE.GetClassNameW(hwnd, clsBuf, 256)
            val clsLen = clsBuf.indexOfFirst { it == '\u0000' }.let { if (it < 0) clsBuf.size else it }
            val cls = String(clsBuf, 0, clsLen)
            if (className != null && cls != className) return@WNDENUMPROC true
            if (!matchAll && titleSubstring.isNotEmpty() && !title.contains(titleSubstring)) return@WNDENUMPROC true
            synchronized(listLock) { results.add(WindowInfo(Pointer.nativeValue(hwnd.pointer), title, cls)) }
            true
        }

        val worker = Thread {
            try {
                User32.INSTANCE.EnumWindows(callback, null)
            } finally {
                done.set(true)
            }
        }
        worker.isDaemon = true
        worker.start()
        worker.join((timeoutSeconds * 1000).toLong())
        if (worker.isAlive) {
            done.set(true)
            worker.join(100)
        }
        return synchronized(listLock) { results.toList() }
    }
}
