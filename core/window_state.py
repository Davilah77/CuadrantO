import re
import sys

from core.settings import load_settings, save_settings


GEOMETRY_RE = re.compile(r"^(\d+)x(\d+)([+-]\d+)([+-]\d+)$")


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
    if saved.get("maximized"):
        try:
            window.state("zoomed")
        except Exception:
            pass

    pending = None
    last_normal = geometry
    last_maximized = bool(saved.get("maximized"))

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
        pending = None
        write_state()

    def changed(event):
        nonlocal pending, last_normal, last_maximized
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
        if pending is not None:
            window.after_cancel(pending)
        pending = window.after(450, persist)

    def destroyed(event):
        if event.widget is window:
            write_state()

    window.bind("<Configure>", changed, add="+")
    window.bind("<Destroy>", destroyed, add="+")
