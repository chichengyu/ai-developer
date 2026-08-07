// Top-level window enumeration via JNA. FindWindowW first, then EnumWindows
// inside a thread guarded by a 3-second timeout. Caches results by
// (class, title-substring) for the current session.
//
// Maven:
//     <dependency>
//         <groupId>net.java.dev.jna</groupId>
//         <artifactId>jna</artifactId>
//         <version>5.14.0</version>
//     </dependency>
import com.sun.jna.Native;
import com.sun.jna.platform.win32.User32;
import com.sun.jna.platform.win32.WinDef.HWND;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public final class WindowEnum {
    private final Map<String, HWND> cache = new HashMap<>();
    private final Object lock = new Object();

    public static final class Info {
        public final HWND hwnd;
        public final String title;
        public final String className;
        public Info(HWND h, String t, String c) { hwnd = h; title = t; className = c; }
    }

    public HWND find(String className, String titleSubstring) {
        String key = (className == null ? "" : className) + "|" + titleSubstring;
        synchronized (lock) {
            HWND cached = cache.get(key);
            if (cached != null && User32.INSTANCE.IsWindow(cached)) return cached;
        }
        if (className != null && !hasWildcards(titleSubstring)) {
            HWND h = User32.INSTANCE.FindWindowW(className, titleSubstring);
            if (h != null) { synchronized (lock) { cache.put(key, h); } return h; }
        }
        List<Info> matches = enumWithTimeout(className, titleSubstring, false);
        if (!matches.isEmpty()) {
            synchronized (lock) { cache.put(key, matches.get(0).hwnd); }
            return matches.get(0).hwnd;
        }
        return null;
    }

    public List<Info> listWindows(String className) {
        return enumWithTimeout(className, "", true);
    }

    public void invalidate() { synchronized (lock) { cache.clear(); } }

    private List<Info> enumWithTimeout(final String className, final String titleSubstring, final boolean matchAll) {
        final List<Info> results = new ArrayList<>();
        final CountDownLatch latch = new CountDownLatch(1);
        final AtomicBoolean stop = new AtomicBoolean(false);

        Thread t = new Thread(() -> {
            try {
                User32.INSTANCE.EnumWindows((hwnd, data) -> {
                    if (stop.get()) return false;
                    char[] titleBuf = new char[User32.INSTANCE.GetWindowTextLengthW(hwnd) + 1];
                    User32.INSTANCE.GetWindowTextW(hwnd, titleBuf, titleBuf.length);
                    String title = Native.toString(titleBuf);
                    char[] clsBuf = new char[256];
                    int n = User32.INSTANCE.GetClassNameW(hwnd, clsBuf, 256);
                    String cls = Native.toString(clsBuf, n);
                    if (title.isEmpty() && !matchAll) return true;
                    if (className != null && !className.equals(cls)) return true;
                    if (!matchAll && !titleSubstring.isEmpty() && !title.contains(titleSubstring)) return true;
                    results.add(new Info(hwnd, title, cls));
                    return true;
                }, null);
            } finally { latch.countDown(); }
        });
        t.setDaemon(true);
        t.start();
        try { latch.await(3, TimeUnit.SECONDS); } catch (InterruptedException ignored) {}
        stop.set(true);
        try { t.join(100); } catch (InterruptedException ignored) {}
        return results;
    }

    private static boolean hasWildcards(String s) { return s.contains("*") || s.contains("?"); }
}