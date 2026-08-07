// Top-level window enumeration via dart:ffi.
// FindWindowW first, then EnumWindows guarded by a 3-second timeout (use
// package:win32 for the typed EnumWindows callback; pure dart:ffi with
// callbacks across isolates is not straightforward).
//
// pubspec.yaml:
//     dependencies:
//       ffi: ^2.1.0
//       win32: ^5.0.0   # required for EnumWindows callback
import 'dart:ffi';
import 'package:ffi/ffi.dart';
import 'package:win32/win32.dart' show EnumWindows, GetWindowText, GetClassName;

class Info {
  final int hwnd;
  final String title;
  final String className;
  Info(this.hwnd, this.title, this.className);
}

class WindowFinder {
  final Map<String, int> _cache = {};
  static const _timeout = Duration(seconds: 3);

  int? find(String? className, String titleSubstring) {
    final key = '${className ?? ""}|\$titleSubstring';
    final cached = _cache[key];
    if (cached != null && IsWindow(cached) != 0) return cached;
    if (className != null && !_hasWildcards(titleSubstring)) {
      final h = FindWindowW(className, titleSubstring);
      if (h != 0) { _cache[key] = h; return h; }
    }
    final matches = listWindows(className);
    if (matches.isNotEmpty) { _cache[key] = matches.first.hwnd; return matches.first.hwnd; }
    return null;
  }

  List<Info> listWindows(String? className) {
    final results = <Info>[];
    final stopwatch = Stopwatch()..start();
    final cancel = Completer<void>();
    Timer(_timeout, () => cancel.complete());
    try {
      EnumWindows((hwnd, _) {
        if (stopwatch.elapsed > _timeout) return false;
        final title = GetWindowText(hwnd);
        final cls = GetClassName(hwnd);
        if (title.isEmpty) return true;
        if (className != null && cls != className) return true;
        results.add(Info(hwnd, title, cls));
        return true;
      });
    } catch (_) {}
    return results;
  }

  void invalidate() => _cache.clear();
  static bool _hasWildcards(String s) => s.contains('*') || s.contains('?');
}