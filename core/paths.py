import sys
from pathlib import Path


APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))
SETTINGS_PATH = APP_DIR / "settings.json"


def resource_path(relative: str) -> Path:
    return BUNDLE_DIR / relative
