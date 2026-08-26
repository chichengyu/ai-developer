// Hardware-level keyboard input via Win32 SendInput, using JNA.
//
// Drop-in:
//     SendInput.sendKey(hwnd, "F5");
//     SendInput.pressCombo(hwnd, "ctrl+shift+F1");
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
import com.sun.jna.Structure;
import com.sun.jna.Structure.FieldOrder;

import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.ThreadLocalRandom;

// Keep the VK map in sync with scripts/vk_table.json (Python is checked automatically).
public final class SendInput {
    private static final int INPUT_KEYBOARD = 1;
    private static final int KEYEVENTF_KEYUP = 0x0002;
    private static final int SW_RESTORE = 9;
    private static final Map<String, Integer> VK = buildVkMap();

    @FieldOrder({"wVk", "wScan", "dwFlags", "time", "dwExtraInfo"})
    public static class KeybdInput extends Structure {
        public short wVk;
        public short wScan;
        public int dwFlags;
        public int time;
        public com.sun.jna.Pointer dwExtraInfo;
    }

    @FieldOrder({"type", "ki"})
    public static class Input extends Structure {
        public int type;
        public KeybdInput ki;
    }

    private SendInput() {}

    private static Map<String, Integer> buildVkMap() {
        Map<String, Integer> m = new HashMap<>();
        for (int i = 0; i < 26; i++) m.put(String.valueOf((char) ('a' + i)), 0x41 + i);
        for (int i = 0; i < 10; i++) m.put(String.valueOf((char) ('0' + i)), 0x30 + i);
        for (int i = 1; i <= 24; i++) m.put("f" + i, 0x70 + i - 1);
        for (int i = 0; i < 10; i++) m.put("num" + i, 0x60 + i);
        Map<String, Integer> extras = new HashMap<>();
        extras.put("back", 0x08); extras.put("tab", 0x09); extras.put("enter", 0x0D);
        extras.put("escape", 0x1B); extras.put("esc", 0x1B); extras.put("space", 0x20);
        extras.put("pageup", 0x21); extras.put("pagedown", 0x22);
        extras.put("end", 0x23); extras.put("home", 0x24);
        extras.put("left", 0x25); extras.put("up", 0x26); extras.put("right", 0x27); extras.put("down", 0x28);
        extras.put("insert", 0x2D); extras.put("delete", 0x2E);
        extras.put("lshift", 0xA0); extras.put("rshift", 0xA1);
        extras.put("lctrl", 0xA2); extras.put("rctrl", 0xA3);
        extras.put("lalt", 0xA4); extras.put("ralt", 0xA5);
        extras.put("lwin", 0x5B); extras.put("rwin", 0x5C);
        extras.put("capslock", 0x14); extras.put("numlock", 0x90); extras.put("scrolllock", 0x91);
        extras.put("semicolon", 0xBA); extras.put("equals", 0xBB);
        extras.put("comma", 0xBC); extras.put("minus", 0xBD);
        extras.put("period", 0xBE); extras.put("slash", 0xBF); extras.put("backtick", 0xC0);
        extras.put("lbracket", 0xDB); extras.put("backslash", 0xDC);
        extras.put("rbracket", 0xDD); extras.put("apostrophe", 0xDE);
        extras.put("select", 0x29); extras.put("print", 0x2A); extras.put("execute", 0x2B);
        extras.put("snapshot", 0x2C); extras.put("help", 0x2F);
        extras.put("nummultiply", 0x6A); extras.put("numadd", 0x6B); extras.put("numseparator", 0x6C);
        extras.put("numsubtract", 0x6D); extras.put("numdecimal", 0x6E); extras.put("numdivide", 0x6F);
        m.putAll(extras);
        return m;
    }

    public static boolean ensureForeground(HWND hwnd) {
        if (hwnd == null) return false;
        for (int i = 0; i < 5; i++) {
            User32.INSTANCE.ShowWindow(hwnd, SW_RESTORE);
            User32.INSTANCE.SetForegroundWindow(hwnd);
            if (User32.INSTANCE.GetForegroundWindow() == hwnd) return true;
            try { Thread.sleep(50); } catch (InterruptedException ignored) {}
        }
        return User32.INSTANCE.GetForegroundWindow() == hwnd;
    }

    public static void sendKey(HWND hwnd, String key, int holdMs) {
        Integer vkCode = VK.get(key.toLowerCase());
        if (vkCode == null) throw new IllegalArgumentException("Unknown key: " + key);
        if (!ensureForeground(hwnd))
            throw new IllegalStateException("Failed to foreground window");
        Input[] one = {new Input()};
        one[0] = makeInput(vkCode, false);
        User32.INSTANCE.SendInput(1, one, one[0].size());
        try { Thread.sleep(holdMs); } catch (InterruptedException ignored) {}
        one[0] = makeInput(vkCode, true);
        User32.INSTANCE.SendInput(1, one, one[0].size());
    }

    public static void pressCombo(HWND hwnd, String combo, int jitterMs) {
        String[] tokens = combo.toLowerCase().split("\\+");
        if (tokens.length == 0) throw new IllegalArgumentException("empty combo");
        String trigger = tokens[tokens.length - 1].trim();
        Integer triggerVk = VK.get(trigger);
        if (triggerVk == null) throw new IllegalArgumentException("Unknown trigger: " + trigger);
        java.util.List<Integer> mods = new java.util.ArrayList<>();
        for (int i = 0; i < tokens.length - 1; i++) {
            String t = tokens[i].trim();
            switch (t) {
                case "ctrl": case "control": mods.add(0xA2); break;
                case "shift": mods.add(0xA0); break;
                case "alt": mods.add(0xA4); break;
                case "win": case "meta": mods.add(0x5B); break;
                default: throw new IllegalArgumentException("Unknown modifier: " + t);
            }
        }
        if (!ensureForeground(hwnd))
            throw new IllegalStateException("Failed to foreground window");
        Input[] oneSize = {new Input()};
        for (int m : mods) {
            oneSize[0] = makeInput(m, false);
            User32.INSTANCE.SendInput(1, oneSize, oneSize[0].size());
        }
        try { Thread.sleep(jitterMs(jitterMs)); } catch (InterruptedException ignored) {}
        oneSize[0] = makeInput(triggerVk, false);
        User32.INSTANCE.SendInput(1, oneSize, oneSize[0].size());
        try { Thread.sleep(jitterMs(jitterMs)); } catch (InterruptedException ignored) {}
        oneSize[0] = makeInput(triggerVk, true);
        User32.INSTANCE.SendInput(1, oneSize, oneSize[0].size());
        try { Thread.sleep(jitterMs(jitterMs)); } catch (InterruptedException ignored) {}
        for (int i = mods.size() - 1; i >= 0; i--) {
            oneSize[0] = makeInput(mods.get(i), true);
            User32.INSTANCE.SendInput(1, oneSize, oneSize[0].size());
        }
    }

    private static Input makeInput(int vkCode, boolean up) {
        KeybdInput ki = new KeybdInput();
        ki.wVk = (short) vkCode;
        ki.wScan = 0;
        ki.dwFlags = up ? KEYEVENTF_KEYUP : 0;
        ki.time = 0;
        ki.dwExtraInfo = null;
        ki.write();
        Input in = new Input();
        in.type = INPUT_KEYBOARD;
        in.ki = ki;
        in.write();
        return in;
    }

    private static int jitterMs(int requested) {
        if (requested > 0) return requested;
        return ThreadLocalRandom.current().nextInt(50, 151);
    }
}
