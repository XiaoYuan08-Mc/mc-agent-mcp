"""游戏内键鼠注入与截图 —— 不塞 mod 的 Windows 原生路径。

输入注入与取帧走 Win32 API，不需要往游戏里装桥接 mod，
跨版本维护成本高。这里换成 Win32：

- 键盘/鼠标：`SendInput` 投递给前台窗口。Minecraft 的 GLFW 后端吃这条路径。
- 截图：优先发 `F2` 让游戏自己存到 `screenshots/`（最可靠，GL 帧缓冲由游戏自己读）；
  兜底用 GDI `BitBlt` 抓窗口区域（窗口必须可见、未被遮挡）。

约束（写死在返回里，不装作没有）：
- 目标窗口必须在前台；后台注入会被 GLFW 丢掉。
- 全屏独占（fullscreen exclusive）下 Alt-Tab 切换可能改变分辨率，建议用窗口化全屏。
- 没有管理员权限时，对以管理员运行的游戏注入无效（UIPI）。
"""

from __future__ import annotations

import ctypes
import os
import time
from ctypes import wintypes
from pathlib import Path

from PIL import Image

from . import state


class InputError(RuntimeError):
    pass


IS_WIN = os.name == "nt"

if IS_WIN:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass

    ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                    ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                    ("dwExtraInfo", ULONG_PTR)]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD),
                    ("wParamH", wintypes.WORD)]

    class _INPUTUNION(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

    class INPUT(ctypes.Structure):
        _anonymous_ = ("u",)
        _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]

    INPUT_KEYBOARD = 1
    INPUT_MOUSE = 0
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_UNICODE = 0x0004
    KEYEVENTF_SCANCODE = 0x0008
    MOUSEEVENTF_MOVE = 0x0001
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004
    MOUSEEVENTF_RIGHTDOWN = 0x0008
    MOUSEEVENTF_RIGHTUP = 0x0010
    MOUSEEVENTF_MIDDLEDOWN = 0x0020
    MOUSEEVENTF_MIDDLEUP = 0x0040
    MOUSEEVENTF_WHEEL = 0x0800

    user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
    user32.SendInput.restype = wintypes.UINT
    user32.MapVirtualKeyW.argtypes = (wintypes.UINT, wintypes.UINT)
    user32.MapVirtualKeyW.restype = wintypes.UINT

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def _send(inputs: list) -> int:
    n = len(inputs)
    if not n:
        return 0
    arr = (INPUT * n)(*inputs)
    sent = user32.SendInput(n, arr, ctypes.sizeof(INPUT))
    if sent != n:
        raise InputError(f"SendInput 只发出 {sent}/{n}（可能是权限或 UIPI 拦截）")
    return sent


def _key_input(vk: int, up: bool = False, scan_only: bool = False) -> "INPUT":
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    flags = (KEYEVENTF_KEYUP if up else 0)
    if scan_only:
        flags |= KEYEVENTF_SCANCODE
        inp.ki.wScan = user32.MapVirtualKeyW(vk, 0)
        inp.ki.wVk = 0
    else:
        inp.ki.wVk = vk
    inp.ki.dwFlags = flags
    return inp


def _unicode_input(ch: str, up: bool = False) -> "INPUT":
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.ki.wVk = 0
    inp.ki.wScan = ord(ch)
    inp.ki.dwFlags = KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if up else 0)
    return inp


VK = {
    "esc": 0x1B, "escape": 0x1B, "enter": 0x0D, "return": 0x0D, "tab": 0x09,
    "space": 0x20, "backspace": 0x08, "shift": 0x10, "ctrl": 0x11, "control": 0x11,
    "alt": 0x12, "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74, "f6": 0x75,
    "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
    "e": 0x45, "q": 0x51, "w": 0x57, "a": 0x41, "s": 0x53, "d": 0x44,
    "i": 0x49, "t": 0x54, "slash": 0xBF, "0": 0x30, "1": 0x31,
}


def _vk_of(key: str) -> int:
    k = (key or "").strip().lower()
    if k in VK:
        return VK[k]
    if len(k) == 1:
        vk = user32.VkKeyScanW(ord(k))
        if vk != -1:
            return vk & 0xFF
        return ord(k.upper())
    raise InputError(f"不认识的按键: {key}")


# --------------------------------------------------------------- 窗口
def windows(keyword: str = "", minecraft_only: bool = False) -> list[dict]:
    if not IS_WIN:
        raise InputError("只有 Windows 支持这条路径")
    rows = []

    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 256)
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        is_mc = cls.value.startswith("GLFW") or "minecraft" in title.lower()
        if keyword and keyword.lower() not in title.lower():
            return True
        if minecraft_only and not is_mc:
            return True
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        rows.append({
            "hwnd": int(hwnd), "title": title, "class": cls.value, "pid": pid.value,
            "minecraft": is_mc,
            "rect": [rect.left, rect.top, rect.right, rect.bottom],
            "size": [rect.right - rect.left, rect.bottom - rect.top],
        })
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return rows


def find_minecraft() -> dict:
    hits = [w for w in windows(minecraft_only=True)
            if "GLFW" in w["class"] or "Minecraft" in w["title"]]
    hits.sort(key=lambda w: -w["size"][0] * w["size"][1])
    if not hits:
        raise InputError("没找到 Minecraft 窗口（窗口化启动后再试；标题通常含 'Minecraft'）")
    return hits[0]


def focus(hwnd: int) -> bool:
    """把窗口抢到前台。Windows 有前台锁，必须先把线程输入队列挂到当前前台线程上。

    顺序很重要：AttachThreadInput 要在 SetForegroundWindow **之前**，
    反了就是"偶尔成功"。最后再用一次 ALT 键技巧兜底（系统会认为用户有交互意图）。
    """
    if not IS_WIN:
        raise InputError("只有 Windows 支持")
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    if user32.GetForegroundWindow() == hwnd:
        return True

    fg = user32.GetForegroundWindow()
    fg_tid = user32.GetWindowThreadProcessId(fg, None)
    cur_tid = kernel32.GetCurrentThreadId()
    attached = False
    if fg_tid and fg_tid != cur_tid:
        attached = bool(user32.AttachThreadInput(cur_tid, fg_tid, True))
    try:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        user32.SetFocus(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(cur_tid, fg_tid, False)

    time.sleep(0.15)
    if user32.GetForegroundWindow() != hwnd:
        # 兜底：模拟一次 ALT，系统会放行接下来的前台切换
        _send([_key_input(0x12), _key_input(0x12, up=True)])
        time.sleep(0.08)
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.15)

    return bool(user32.GetForegroundWindow() == hwnd)


# --------------------------------------------------------------- 输入
def key_tap(key: str, hold_ms: int = 60, modifier: str = "") -> dict:
    vk = _vk_of(key)
    mods = [_vk_of(m) for m in modifier.split("+") if m.strip()] if modifier else []
    seq = []
    for m in mods:
        seq.append(_key_input(m))
    seq.append(_key_input(vk))
    seq.append(_key_input(vk, up=True))
    for m in reversed(mods):
        seq.append(_key_input(m, up=True))
    _send(seq)
    time.sleep(max(0, hold_ms) / 1000.0)
    return {"key": key, "vk": vk, "modifier": modifier, "hold_ms": hold_ms}


def key_hold(key: str, duration_ms: int = 300) -> dict:
    vk = _vk_of(key)
    _send([_key_input(vk)])
    time.sleep(max(0, duration_ms) / 1000.0)
    _send([_key_input(vk, up=True)])
    return {"key": key, "held_ms": duration_ms}


def type_text(text: str) -> dict:
    seq = []
    for ch in text:
        if ch == "\n":
            seq.append(_key_input(0x0D))
            seq.append(_key_input(0x0D, up=True))
            continue
        seq.append(_unicode_input(ch))
        seq.append(_unicode_input(ch, up=True))
    _send(seq)
    return {"typed": text, "chars": len(text)}


def mouse_move(dx: int, dy: int) -> dict:
    """相对移动。用 mouse_event 而不是 SendInput：GLFW/部分窗口对后者的 MOUSEEVENTF_MOVE 不敏感。"""
    user32.mouse_event(MOUSEEVENTF_MOVE, int(dx), int(dy), 0, 0)
    return {"dx": dx, "dy": dy}


def move_to(x: int, y: int) -> dict:
    """绝对定位光标（屏幕坐标）。点窗口前先定位比盲点可靠。"""
    if not user32.SetCursorPos(int(x), int(y)):
        raise InputError(f"SetCursorPos 失败: ({x},{y})")
    return {"cursor": [int(x), int(y)]}


def window_center(hwnd: int) -> tuple[int, int]:
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return ((rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2)


def mouse_click(button: str = "left", count: int = 1, at: tuple[int, int] | None = None) -> dict:
    down, up = {
        "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
        "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
        "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
    }.get((button or "left").lower(), (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP))
    if at:
        move_to(*at)
        time.sleep(0.12)
    for _ in range(max(1, count)):
        user32.mouse_event(down, 0, 0, 0, 0)
        time.sleep(0.03)
        user32.mouse_event(up, 0, 0, 0, 0)
        time.sleep(0.06)
    return {"button": button, "count": count, "at": list(at) if at else None}


def scroll(amount: int) -> dict:
    user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, int(amount) * 120, 0)
    return {"wheel": amount}


# --------------------------------------------------------------- 截图
def _grab_screen_rect(rect: list[int], out_path: str) -> str:
    left, top, right, bottom = rect
    w, h = right - left, bottom - top
    if w <= 0 or h <= 0:
        raise InputError(f"窗口尺寸异常: {rect}")

    hdc_screen = user32.GetDC(0)
    hdc_mem = ctypes.windll.gdi32.CreateCompatibleDC(hdc_screen)
    hbmp = ctypes.windll.gdi32.CreateCompatibleBitmap(hdc_screen, w, h)
    ctypes.windll.gdi32.SelectObject(hdc_mem, hbmp)
    SRCCOPY = 0x00CC0020
    ok = ctypes.windll.gdi32.BitBlt(hdc_mem, 0, 0, w, h, hdc_screen, left, top, SRCCOPY)

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                    ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                    ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                    ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD)]

    bi = BITMAPINFOHEADER()
    bi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bi.biWidth = w
    bi.biHeight = -h
    bi.biPlanes = 1
    bi.biBitCount = 32
    bi.biCompression = 0
    buf = ctypes.create_string_buffer(w * h * 4)
    got = ctypes.windll.gdi32.GetDIBits(hdc_mem, hbmp, 0, h, buf, ctypes.byref(bi), 0)

    ctypes.windll.gdi32.DeleteObject(hbmp)
    ctypes.windll.gdi32.DeleteDC(hdc_mem)
    user32.ReleaseDC(0, hdc_screen)
    if not ok or got == 0:
        raise InputError("BitBlt 抓屏失败（窗口可能被遮挡或最小化）")

    img = Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(out)
    return str(out)


def screenshot_live(out_dir: str, timeout: float = 6.0) -> dict:
    """发 F2 让游戏自己截图，然后从 screenshots 目录捞新文件。"""
    d = Path(out_dir).expanduser().resolve()
    d.mkdir(parents=True, exist_ok=True)
    before = {p.name: p.stat().st_mtime for p in d.glob("*.png")}
    key_tap("f2", hold_ms=80)
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(0.4)
        for p in sorted(d.glob("*.png"), key=lambda x: x.stat().st_mtime, reverse=True):
            if p.name not in before or p.stat().st_mtime > before.get(p.name, 0):
                return {"output": str(p), "method": "in-game F2", "size_bytes": p.stat().st_size}
    raise InputError(f"{timeout}s 内 screenshots 目录没出现新图（{d}）；确认按键生效、游戏在前台")


def _print_window(hwnd: int, out_path: str) -> dict:
    """PrintWindow(PW_RENDERFULLCONTENT)：对被遮挡的普通窗口也有效，GL 窗口一般拿不到。"""
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w, h = rect.right - rect.left, rect.bottom - rect.top
    if w <= 0 or h <= 0:
        raise InputError(f"窗口尺寸异常: {w}x{h}")

    hdc_screen = user32.GetDC(0)
    hdc_mem = ctypes.windll.gdi32.CreateCompatibleDC(hdc_screen)
    hbmp = ctypes.windll.gdi32.CreateCompatibleBitmap(hdc_screen, w, h)
    ctypes.windll.gdi32.SelectObject(hdc_mem, hbmp)
    ok = user32.PrintWindow(hwnd, hdc_mem, 2)

    class BIH(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                    ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                    ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                    ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD)]

    bi = BIH()
    bi.biSize = ctypes.sizeof(BIH)
    bi.biWidth = w
    bi.biHeight = -h
    bi.biPlanes = 1
    bi.biBitCount = 32
    bi.biCompression = 0
    buf = ctypes.create_string_buffer(w * h * 4)
    got = ctypes.windll.gdi32.GetDIBits(hdc_mem, hbmp, 0, h, buf, ctypes.byref(bi), 0)
    ctypes.windll.gdi32.DeleteObject(hbmp)
    ctypes.windll.gdi32.DeleteDC(hdc_mem)
    user32.ReleaseDC(0, hdc_screen)
    if not ok or got == 0:
        raise InputError("PrintWindow 失败")

    img = Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1).convert("RGB")
    colors = img.resize((32, 32)).getcolors(maxcolors=4096) or []
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return {"output": str(out), "size": [w, h], "method": "PrintWindow",
            "uniform_frame": len(colors) <= 2}


def screenshot_window(hwnd: int, out_path: str, focus_first: bool = True,
                      prefer: str = "bitblt") -> dict:
    """取帧。prefer=bitblt（默认，游戏/GL/UWP 唯一可靠）| printwindow（普通 Win32 窗口）。

    PrintWindow 对 WinUI/UWP 只能拿到空壳布局（有矩形没内容），对 GL 窗口直接黑屏，
    所以默认走"抢前台 + BitBlt"。要截后台普通窗口再显式传 prefer=printwindow。
    """
    if prefer == "printwindow" or not focus_first:
        try:
            res = _print_window(hwnd, out_path)
            if not res["uniform_frame"]:
                return {**res, "target_hwnd": hwnd}
        except Exception:
            pass

    if focus_first:
        focus(hwnd)
        time.sleep(0.45)
    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise InputError("拿不到窗口矩形")
    path = _grab_screen_rect([rect.left, rect.top, rect.right, rect.bottom], out_path)
    img = Image.open(path)
    colors = img.resize((32, 32)).getcolors(maxcolors=4096) or []
    uniform = len(colors) <= 2
    return {
        "output": path,
        "size": list(img.size),
        "method": "GDI BitBlt（已抢前台）",
        "target_hwnd": hwnd,
        "uniform_frame": uniform,
        "warning": ("画面接近纯色：独占全屏、被遮挡或最小化。"
                    "可靠取帧请用 mc_capture 的 ingame 模式（游戏内 F2）") if uniform else "",
    }


# --------------------------------------------------------------- 编排
def game_action(action: str, key: str = "", modifier: str = "", text: str = "",
                duration_ms: int = 0, button: str = "left", x: int = 0, y: int = 0,
                hwnd: int = 0, focus_first: bool = True) -> dict:
    """把单个动作落到游戏窗口上。action: key / hold / text / click / move / scroll / focus。"""
    win = {"hwnd": hwnd} if hwnd else find_minecraft()
    target = win["hwnd"]
    focused = focus(target) if focus_first else None

    act = (action or "").lower()
    began = time.time()
    if act in ("focus", "status"):
        payload = {"focused": bool(focused), "window": win}
    elif act == "key":
        _send([_key_input(_vk_of(key))])
        time.sleep(max(30, duration_ms or 60) / 1000.0)
        _send([_key_input(_vk_of(key), up=True)])
        payload = {"key": key, "duration_ms": duration_ms or 60}
    elif act == "hold":
        payload = key_hold(key, duration_ms or 300)
    elif act == "text":
        payload = type_text(text)
    elif act == "click":
        payload = mouse_click(button, int(x or 1))
    elif act == "move":
        payload = mouse_move(int(x), int(y))
    elif act == "scroll":
        payload = scroll(int(y or 1))
    else:
        raise InputError(f"未知 action: {action}（key/hold/text/click/move/scroll/focus/status）")

    payload.update({
        "action": act,
        "hwnd": target,
        "focused": bool(focused),
        "elapsed_ms": int((time.time() - began) * 1000),
        "note": "注入到前台窗口；窗口失焦时 Minecraft 会丢弃输入",
    })
    if not focused and focus_first:
        payload["warning"] = "窗口没抢到前台，输入可能被系统丢掉"
    return payload
