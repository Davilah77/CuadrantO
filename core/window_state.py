import re
import sys
import time

from core.settings import load_settings, save_settings


GEOMETRY_RE = re.compile(r"^(\d+)x(\d+)([+-]\d+)([+-]\d+)$")


def apply_native_titlebar(window) -> None:
    """Match the Windows title bar to the application's saved theme."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        window.update_idletasks()
        user32 = ctypes.windll.user32
        hwnd = user32.GetParent(window.winfo_id()) or window.winfo_id()
        dark = ctypes.c_int(str(load_settings().get("appearance_mode", "Dark")).lower() == "dark")
        # Windows 10 used attribute 19 before standardising it as 20.
        for attribute in (20, 19):
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, attribute, ctypes.byref(dark), ctypes.sizeof(dark)
            ) == 0:
                break
        user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0027)
    except Exception:
        pass


def _screen_bounds(window) -> tuple[int, int, int, int]:
    if sys.platform == "win32":
        try:
            import ctypes

            user32 = ctypes.windll.user32
            return tuple(user32.GetSystemMetrics(index) for index in (76, 77, 78, 79))
        except Exception:
            pass
    return (window.winfo_vrootx(), window.winfo_vrooty(), window.winfo_vrootwidth(), window.winfo_vrootheight())


def _visible_geometry(window, geometry: str) -> str | None:
    match = GEOMETRY_RE.match(str(geometry))
    if not match:
        return None
    width, height, x, y = map(int, match.groups())
    left, top, screen_width, screen_height = _screen_bounds(window)
    width = max(240, min(width, screen_width))
    height = max(160, min(height, screen_height))
    right = left + screen_width
    bottom = top + screen_height
    visible = 80
    x = max(left - width + visible, min(x, right - visible))
    y = max(top, min(y, bottom - visible))
    return f"{width}x{height}{x:+d}{y:+d}"


def remember_window(window, key: str, default_geometry: str) -> None:
    """Restore and continuously remember a top-level window's placement."""
    saved = load_settings().get("window_layouts", {}).get(key, {})
    geometry = _visible_geometry(window, saved.get("geometry", "")) or default_geometry
    window.geometry(geometry)
    window.update_idletasks()
    apply_native_titlebar(window)
    window.after(20, lambda: apply_native_titlebar(window))
    if saved.get("maximized"):
        try:
            window.state("zoomed")
        except Exception:
            pass

    pending = None
    last_normal = geometry
    last_maximized = bool(saved.get("maximized"))
    last_change = 0.0

    def write_state():
        try:
            values = load_settings()
            layouts = dict(values.get("window_layouts", {}))
            layouts[key] = {"geometry": last_normal, "maximized": last_maximized}
            values["window_layouts"] = layouts
            save_settings(values)
        except Exception:
            pass

    def persist():
        nonlocal pending
        remaining = 0.45 - (time.monotonic() - last_change)
        if remaining > 0:
            pending = window.after(max(50, int(remaining * 1000)), persist)
            return
        pending = None
        write_state()

    def changed(event):
        nonlocal pending, last_normal, last_maximized, last_change
        if event.widget is not window:
            return
        try:
            state = window.state()
            last_maximized = state == "zoomed"
            if state == "normal":
                current = _visible_geometry(window, window.geometry())
                if current:
                    last_normal = current
        except Exception:
            return
        last_change = time.monotonic()
        # Keep a single lightweight timer while Windows emits dozens of
        # Configure events during a drag or maximize operation.
        if pending is None:
            pending = window.after(450, persist)

    def destroyed(event):
        if event.widget is window:
            write_state()

    window.bind("<Configure>", changed, add="+")
    window.bind("<Destroy>", destroyed, add="+")
    window.bind(
        "<Map>", lambda event: apply_native_titlebar(window) if event.widget is window else None, add="+"
    )
