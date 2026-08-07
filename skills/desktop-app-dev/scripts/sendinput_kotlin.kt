/**
 * Kotlin/JVM SendInput via JNA. Works on Windows; on macOS/Linux throws.
 *
 * Mirrors scripts/SendInput.java but with idiomatic Kotlin (no JNI boilerplate).
 *
 * Build:
 *   dependencies { implementation("net.java.dev.jna:jna:5.14.0") }
 *
 * Usage:
 *   import desktop.SendInput
 *   SendInput.sendKey(hwnd, "F5")
 *   SendInput.pressCombo(hwnd, "ctrl+shift+F1")
 */
package desktop

import com.sun.jna.Native
import com.sun.jna.Pointer
import com.sun.jna.Structure
import com.sun.jna.platform.win32.User32
import com.sun.jna.platform.win32.WinDef
import com.sun.jna.win32.StdCallLibrary
import kotlin.random.Random

object SendInput {

    // ---- VK table -----------------------------------------------------------
    // Keep this map in sync with scripts/vk_table.json (Python is checked automatically).
    val VK: Map<String, Int> = linkedMapOf(
        // letters
        *((0x41..0x5A).map { ('A' + (it - 0x41)).lowercaseChar() to it }.toTypedArray()),
        // digits
        *((0x30..0x39).map { ('0' + (it - 0x30)) to it }.toTypedArray()),
        // function keys F1-F24
        *(1..24).map { "f$it" to (0x6F + it - 1) }.toTypedArray(),
        // numpad
        *(0..9).map { "num$it" to (0x60 + it) }.toTypedArray(),
        "back" to 0x08, "tab" to 0x09, "enter" to 0x0D, "escape" to 0x1B, "esc" to 0x1B,
        "space" to 0x20, "pageup" to 0x21, "pagedown" to 0x22, "end" to 0x23, "home" to 0x24,
        "left" to 0x25, "up" to 0x26, "right" to 0x27, "down" to 0x28,
        "insert" to 0x2D, "delete" to 0x2E,
        "lshift" to 0xA0, "rshift" to 0xA1, "lctrl" to 0xA2, "rctrl" to 0xA3,
        "lalt" to 0xA4, "ralt" to 0xA5, "lwin" to 0x5B, "rwin" to 0x5C,
        "capslock" to 0x14, "numlock" to 0x90, "scrolllock" to 0x91,
        "semicolon" to 0xBA, "equals" to 0xBB, "comma" to 0xBC, "minus" to 0xBD,
        "period" to 0xBE, "slash" to 0xBF, "backtick" to 0xC0,
        "lbracket" to 0xDB, "backslash" to 0xDC, "rbracket" to 0xDD, "apostrophe" to 0xDE,
        "select" to 0x29, "print" to 0x2A, "execute" to 0x2B, "snapshot" to 0x2C, "help" to 0x2F,
        "nummultiply" to 0x6A, "numadd" to 0x6B, "numseparator" to 0x6C,
        "numsubtract" to 0x6D, "numdecimal" to 0x6E, "numdivide" to 0x6F
    )

    private val MOD_ALIAS = mapOf(
        "ctrl" to listOf("lctrl"), "control" to listOf("lctrl"),
        "shift" to listOf("lshift"),
        "alt" to listOf("lalt"),
        "win" to listOf("lwin"), "meta" to listOf("lwin")
    )

    private const val KEYEVENTF_KEYUP = 0x0002

    init {
        if (!System.getProperty("os.name").lowercase().contains("win")) {
            throw UnsupportedOperationException("SendInput is Windows-only.")
        }
    }

    // ---- Win32 structs ------------------------------------------------------
    @Structure.FieldOrder("wVk", "wScan", "dwFlags", "time", "dwExtraInfo")
    open class KeyBdInput : Structure() {
        @JvmField var wVk: Short = 0
        @JvmField var wScan: Short = 0
        @JvmField var dwFlags: Int = 0
        @JvmField var time: Int = 0
        @JvmField var dwExtraInfo: Pointer? = null
    }

    @Structure.FieldOrder("type", "ki")
    open class Input : Structure() {
        @JvmField var type: Int = 1  // INPUT_KEYBOARD
        @JvmField var ki: KeyBdInput = KeyBdInput()
    }

    // ---- Helpers ------------------------------------------------------------
    private fun user32(): User32 = User32.INSTANCE

    private fun ensureForeground(hwnd: WinDef.HWND): Boolean {
        if (hwnd == null) return false
        user32().ShowWindow(hwnd, com.sun.jna.platform.win32.WinUser.SW_RESTORE)
        user32().SetForegroundWindow(hwnd)
        return user32().GetForegroundWindow() == hwnd
    }

    private fun press(vk: Int, up: Boolean): Input {
        val inp = Input()
        inp.type = 1
        inp.ki.wVk = vk.toShort()
        inp.ki.dwFlags = if (up) KEYEVENTF_KEYUP else 0
        inp.write()
        return inp
    }

    private fun sendAll(inputs: Array<Input>): Int {
        if (inputs.isEmpty()) return 0
        val cbSize = Native.getNativeSize(Input::class.java)
        return User32Extra.INSTANCE.SendInput(
            inputs.size,
            Pointer.nativeValue(inputs[0].pointer),
            cbSize
        )
    }

    // ---- Public API ---------------------------------------------------------
    @JvmStatic
    fun sendKey(hwnd: WinDef.HWND, key: String, holdMs: Long = 50L) {
        val vk = VK[key.lowercase()] ?: throw IllegalArgumentException("Unknown key: $key")
        require(ensureForeground(hwnd)) { "Failed to foreground window" }
        sendAll(arrayOf(press(vk, false)))
        Thread.sleep(holdMs)
        sendAll(arrayOf(press(vk, true)))
    }

    @JvmStatic
    fun pressCombo(hwnd: WinDef.HWND, combo: String, jitterMs: Long = 0L) {
        val tokens = combo.split("+").map { it.trim().lowercase() }.filter { it.isNotEmpty() }
        require(tokens.isNotEmpty()) { "empty combo" }
        val trigger = tokens.last()
        val triggerVk = VK[trigger] ?: throw IllegalArgumentException("Unknown trigger: $trigger")
        val mods = tokens.dropLast().flatMap { tok ->
            MOD_ALIAS[tok] ?: throw IllegalArgumentException("Unknown modifier: $tok")
        }
        require(ensureForeground(hwnd)) { "Failed to foreground window" }
        mods.forEach { sendAll(arrayOf(press(VK[it]!!, false))) }
        Thread.sleep(jitterMs(jitterMs))
        sendAll(arrayOf(press(triggerVk, false)))
        Thread.sleep(jitterMs(jitterMs))
        sendAll(arrayOf(press(triggerVk, true)))
        Thread.sleep(jitterMs(jitterMs))
        mods.reversed().forEach { sendAll(arrayOf(press(VK[it]!!, true))) }
    }

    private fun jitterMs(requested: Long): Long =
        if (requested > 0L) requested else Random.nextInt(50, 151).toLong()

    /** Raw SendInput signature -- JNA does not expose this directly. */
    private interface User32Extra : StdCallLibrary {
        companion object {
            val INSTANCE = Native.load("user32", User32Extra::class.java,
                com.sun.jna.Native.getDefaultStringEncoding())
        }
        fun SendInput(nInputs: Int, pInputs: Long, cbSize: Int): Int
    }
}

