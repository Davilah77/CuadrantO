import shutil
from datetime import datetime

from core.settings import backup_directory, configured_path, load_settings


def backup_on_start_if_enabled():
    if not load_settings().get("backup_on_start"):
        return None
    source = configured_path("database_path")
    destination = backup_directory()
    if not source.exists() or destination is None:
        return None
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / f"cuadrante_{datetime.now():%Y%m%d_%H%M%S}.db"
    shutil.copy2(source, target)
    return target

