import json
import os
from pathlib import Path

from core.paths import APP_DIR, SETTINGS_PATH


DEFAULT_SETTINGS = {
    "app_name": "CuadrantO",
    "font_scale": 1.0,
    "appearance_mode": "Dark",
    "logo_path": "",
    "reports_directory": "informes",
    "database_path": "cuadrante.db",
    "backup_on_start": False,
    "backup_directory": "",
    "check_updates_on_start": True,
    "include_prereleases": True,
    "window_layouts": {},
    "coverage": {
        "desayuno": {"yellow": 4, "green": 5, "purple": 6},
        "almuerzo": {"yellow": 5, "green": 6, "purple": 7},
        "cena": {"yellow": 5, "green": 6, "purple": 7},
    },
}


def load_settings() -> dict:
    settings = dict(DEFAULT_SETTINGS)
    settings["coverage"] = {key: dict(value) for key, value in DEFAULT_SETTINGS["coverage"].items()}
    try:
        saved = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        if isinstance(saved, dict):
            coverage = saved.pop("coverage", None)
            settings.update(saved)
            if isinstance(coverage, dict):
                for service, values in coverage.items():
                    if service in settings["coverage"] and isinstance(values, dict):
                        settings["coverage"][service].update(values)
    except (OSError, TypeError, json.JSONDecodeError):
        pass
    return settings


def save_settings(values: dict) -> None:
    SETTINGS_PATH.write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding="utf-8")


def configured_path(key: str) -> Path:
    value = Path(str(load_settings().get(key) or DEFAULT_SETTINGS[key])).expanduser()
    return value if value.is_absolute() else APP_DIR / value


def detected_onedrive() -> Path | None:
    for variable in ("OneDriveCommercial", "OneDrive", "OneDriveConsumer"):
        value = os.environ.get(variable)
        if value and Path(value).exists():
            return Path(value)
    return None


def backup_directory() -> Path | None:
    value = str(load_settings().get("backup_directory") or "").strip()
    if value:
        path = Path(value).expanduser()
        return path if path.is_absolute() else APP_DIR / path
    root = detected_onedrive()
    return root / "CuadrantO" / "Backups" if root else None


def app_logo_path() -> Path | None:
    value = str(load_settings().get("logo_path") or "").strip()
    if value:
        path = Path(value).expanduser()
        return path if path.is_absolute() else APP_DIR / path
    return None
