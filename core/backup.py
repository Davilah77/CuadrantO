import sqlite3
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
    return create_database_backup(destination, "inicio")


def create_database_backup(destination=None, reason="copia"):
    source = configured_path("database_path")
    if not source.exists():
        return None
    destination = destination or backup_directory() or source.parent / "Backups"
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / f"cuadranto_{reason}_{datetime.now():%Y%m%d_%H%M%S}.db"
    with sqlite3.connect(source) as source_conn, sqlite3.connect(target) as target_conn:
        source_conn.backup(target_conn)
    return target
