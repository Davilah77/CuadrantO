import json
import os
import sys
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
    "coverage_mode": "manual",
    "automatic_coverage": {
        "count_maitre": True,
        "count_second_maitre": True,
        "count_sector_heads": True,
    },
    "coverage": {
        "desayuno": {"yellow": 4, "green": 5, "purple": 6},
        "almuerzo": {"yellow": 5, "green": 6, "purple": 7},
        "cena": {"yellow": 5, "green": 6, "purple": 7},
    },
}


def load_settings() -> dict:
    settings = dict(DEFAULT_SETTINGS)
    settings["coverage"] = {key: dict(value) for key, value in DEFAULT_SETTINGS["coverage"].items()}
    settings["automatic_coverage"] = dict(DEFAULT_SETTINGS["automatic_coverage"])
    try:
        saved = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        if isinstance(saved, dict):
            coverage = saved.pop("coverage", None)
            automatic_coverage = saved.pop("automatic_coverage", None)
            settings.update(saved)
            if isinstance(coverage, dict):
                for service, values in coverage.items():
                    if service in settings["coverage"] and isinstance(values, dict):
                        settings["coverage"][service].update(values)
            if isinstance(automatic_coverage, dict):
                settings["automatic_coverage"].update(automatic_coverage)
    except (OSError, TypeError, json.JSONDecodeError):
        pass
    return settings


def save_settings(values: dict) -> None:
    SETTINGS_PATH.write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding="utf-8")


def configured_path(key: str) -> Path:
    value = Path(str(load_settings().get(key) or DEFAULT_SETTINGS[key])).expanduser()
    return value if value.is_absolute() else APP_DIR / value


def detected_onedrive() -> Path | None:
    candidates = []
    for variable in ("OneDriveCommercial", "OneDrive", "OneDriveConsumer"):
        value = os.environ.get(variable)
        if value:
            candidates.append(Path(value))

    # The environment variables are not always inherited by packaged apps.
    # OneDrive keeps the authoritative sync roots in the current user's registry.
    if sys.platform == "win32":
        try:
            import winreg

            accounts = r"Software\Microsoft\OneDrive\Accounts"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, accounts) as root:
                index = 0
                while True:
                    try:
                        account = winreg.EnumKey(root, index)
                    except OSError:
                        break
                    index += 1
                    try:
                        with winreg.OpenKey(root, account) as key:
                            candidates.append(Path(winreg.QueryValueEx(key, "UserFolder")[0]))
                    except OSError:
                        continue

            # Older OneDrive clients and some managed installations publish
            # their root in one of these per-user registry locations instead.
            registry_values = (
                (r"Software\Microsoft\OneDrive", ("UserFolder",)),
                (r"Environment", ("OneDriveCommercial", "OneDrive", "OneDriveConsumer")),
                (
                    r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
                    ("OneDrive", "{A52BBA46-E9E1-435f-B3D9-28DAA648C0F6}"),
                ),
            )
            for key_path, value_names in registry_values:
                try:
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                        for value_name in value_names:
                            try:
                                value = winreg.QueryValueEx(key, value_name)[0]
                                candidates.append(Path(os.path.expandvars(str(value))))
                            except OSError:
                                continue
                except OSError:
                    continue
        except (ImportError, OSError):
            pass

    home = Path.home()
    candidates.extend((home / "OneDrive", home / "OneDrive - Personal"))
    try:
        candidates.extend(path for path in home.glob("OneDrive - *") if path.is_dir())
    except OSError:
        pass

    seen = set()
    for candidate in candidates:
        try:
            normalized = candidate.expanduser().resolve()
        except OSError:
            continue
        key = str(normalized).casefold()
        if key not in seen and normalized.is_dir():
            return normalized
        seen.add(key)
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
