// Hardware-level keyboard input via Win32 SendInput, using dart:ffi.
//
// Drop-in:
//     await sendKey(hwnd, "F5");
//     await pressCombo(hwnd, "ctrl+shift+F1");
//
// pubspec.yaml:
//     dependencies:
//       ffi: ^2.1.0
//       win32: ^5.0.0    # optional, for typed bindings
import 'dart:ffi';
import 'dart:math';
import 'package:ffi/ffi.dart';

final user32 = DynamicLibrary.open('user32.dll');

final _showWindow = user32.lookupFunction<
    Int32 Function(IntPtr, Int32), int Function(int, int)>('ShowWindow');
final _setForegroundWindow = user32.lookupFunction<
    Bool Function(IntPtr), bool Function(int)>('SetForegroundWindow');
final _getForegroundWindow = user32.lookupFunction<
    IntPtr Function(), int Function()>('GetForegroundWindow');
final _sendInputNative = user32.lookupFunction<
    Int32 Function(Uint32, Pointer, Int32),
    int Function(int, Pointer, int)>('SendInput');

const int _inputKeyboard = 1;
const int _keyeventfKeyup = 0x0002;
const int _swRestore = 9;
final _random = Random();

// Keep _buildVkMap() in sync with scripts/vk_table.json (Python is checked automatically).
final Map<String, int> vk = _buildVkMap();

Map<String, int> _buildVkMap() {
  final m = <String, int>{};
  for (var i = 0; i < 26; i++) m[String.fromCharCode(0x61 + i)] = 0x41 + i;
  for (var i = 0; i < 10; i++) m['\$i'] = 0x30 + i;
  for (var i = 1; i <= 24; i++) m['f\$i'] = 0x70 + i - 1;
  for (var i = 0; i < 10; i++) m['num\$i'] = 0x60 + i;
  m.addAll({
    'back': 0x08, 'tab': 0x09, 'enter': 0x0D, 'escape': 0x1B, 'esc': 0x1B,
    'space': 0x20, 'pageup': 0x21, 'pagedown': 0x22, 'end': 0x23, 'home': 0x24,
    'left': 0x25, 'up': 0x26, 'right': 0x27, 'down': 0x28,
    'insert': 0x2D, 'delete': 0x2E,
    'lshift': 0xA0, 'rshift': 0xA1, 'lctrl': 0xA2, 'rctrl': 0xA3,
    'lalt': 0xA4, 'ralt': 0xA5, 'lwin': 0x5B, 'rwin': 0x5C,
    'capslock': 0x14, 'numlock': 0x90, 'scrolllock': 0x91,
    'semicolon': 0xBA, 'equals': 0xBB, 'comma': 0xBC, 'minus': 0xBD,
    'period': 0xBE, 'slash': 0xBF, 'backtick': 0xC0,
    'lbracket': 0xDB, 'backslash': 0xDC, 'rbracket': 0xDD, 'apostrophe': 0xDE,
    'select': 0x29, 'print': 0x2A, 'execute': 0x2B, 'snapshot': 0x2C, 'help': 0x2F,
    'nummultiply': 0x6A, 'numadd': 0x6B, 'numseparator': 0x6C,
    'numsubtract': 0x6D, 'numdecimal': 0x6E, 'numdivide': 0x6F,
  });
  return m;
}

bool _ensureForeground(int hwnd) {
  if (hwnd == 0) return false;
  _showWindow(hwnd, _swRestore);
  _setForegroundWindow(hwnd);
  return _getForegroundWindow() == hwnd;
}

int _jitterMs(int requested) =>
    requested > 0 ? requested : 50 + _random.nextInt(101);

void _pressSingle(int vkCode, bool up) {
  final p = calloc<InputStruct>();
  p.type = _inputKeyboard;
  p.ki.wVk = vkCode;
  p.ki.wScan = 0;
  p.ki.dwFlags = up ? _keyeventfKeyup : 0;
  p.ki.time = 0;
  p.ki.dwExtraInfo = 0;
  _sendInputNative(1, p.cast(), sizeOf<InputStruct>());
  calloc.free(p);
}

Future<void> sendKey(int hwnd, String key, {int holdMs = 50}) async {
  final v = vk[key.toLowerCase()];
  if (v == null) throw ArgumentError('Unknown key: \$key');
  if (!_ensureForeground(hwnd)) throw StateError('Failed to foreground window');
  _pressSingle(v, false);
  await Future.delayed(Duration(milliseconds: holdMs));
  _pressSingle(v, true);
}

Future<void> pressCombo(int hwnd, String combo, {int jitterMs = 0}) async {
  final tokens = combo.toLowerCase().split('+').map((s) => s.trim()).where((s) => s.isNotEmpty).toList();
  if (tokens.isEmpty) throw ArgumentError('empty combo');
  final trigger = tokens.last;
  final triggerVk = vk[trigger];
  if (triggerVk == null) throw ArgumentError('Unknown trigger key: \$trigger');
  final mods = <int>[];
  for (final t in tokens.take(tokens.length - 1)) {
    switch (t) {
      case 'ctrl': case 'control': mods.add(0xA2); break;
      case 'shift': mods.add(0xA0); break;
      case 'alt': mods.add(0xA4); break;
      case 'win': case 'meta': mods.add(0x5B); break;
      default: throw ArgumentError('Unknown modifier: \$t');
    }
  }
  if (!_ensureForeground(hwnd)) throw StateError('Failed to foreground window');
  for (final m in mods) _pressSingle(m, false);
  await Future.delayed(Duration(milliseconds: _jitterMs(jitterMs)));
  _pressSingle(triggerVk, false);
  await Future.delayed(Duration(milliseconds: _jitterMs(jitterMs)));
  _pressSingle(triggerVk, true);
  await Future.delayed(Duration(milliseconds: _jitterMs(jitterMs)));
  for (final m in mods.reversed) _pressSingle(m, true);
}

class KeybdInputStruct extends Struct {
  @Uint16() external int wVk;
  @Uint16() external int wScan;
  @Uint32() external int dwFlags;
  @Uint32() external int time;
  @IntPtr() external int dwExtraInfo;
}

class InputStruct extends Struct {
  @Uint32() external int type;
  external KeybdInputStruct ki;
}
