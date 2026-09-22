import unittest
import hashlib
import io
import shutil
import zipfile
from contextlib import closing
from datetime import date
from pathlib import Path
from unittest.mock import patch

from core import database
from core import updater
from core.updater import UpdateInfo, is_newer, version_key
from modules.cuadrante import parse_week


class CuadranteTests(unittest.TestCase):
    def setUp(self):
        self.db_path = Path(__file__).parent / "_test.db"
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(str(self.db_path) + suffix)
            if candidate.exists():
                candidate.unlink()
        self.path_patch = patch("core.database.configured_path", return_value=self.db_path)
        self.path_patch.start()
        database.initialize_database()

    def tearDown(self):
        self.path_patch.stop()
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(str(self.db_path) + suffix)
            if candidate.exists():
                candidate.unlink()

    def test_week_is_normalized_to_monday(self):
        self.assertEqual(parse_week("23/09/2026"), date(2026, 9, 21))
        self.assertEqual(parse_week("2026-09-27"), date(2026, 9, 21))

    def test_default_catalogues_are_created_once(self):
        database.initialize_database()
        with closing(database.connect()) as conn:
            employees = conn.execute("SELECT COUNT(*) FROM empleados").fetchone()[0]
            shifts = conn.execute("SELECT COUNT(*) FROM turnos").fetchone()[0]
        self.assertEqual(employees, len(database.DEFAULT_EMPLOYEES))
        self.assertEqual(shifts, len(database.DEFAULT_SHIFTS))

    def test_special_statuses_are_not_shifts(self):
        with closing(database.connect()) as conn:
            rows = conn.execute(
                "SELECT codigo FROM turnos WHERE UPPER(codigo) IN ('DESCANSO','PROPIO','BAJA','FALTA')"
            ).fetchall()
        self.assertEqual(rows, [])

    def test_opening_turns_match_business_rule(self):
        with closing(database.connect()) as conn:
            opening = {row["codigo"] for row in conn.execute("SELECT codigo FROM turnos WHERE apertura=1")}
        self.assertEqual(opening, {"d1", "dc1", "dc2", "dc3", "dc4", "dc5", "dc6"})

    def test_g1_is_guard_shift_for_lunch_and_dinner(self):
        with closing(database.connect()) as conn:
            shift = conn.execute("SELECT * FROM turnos WHERE codigo='g1'").fetchone()
        self.assertEqual((shift["entrada_tarde"], shift["salida_tarde"], shift["horas"]), ("14:00", "22:00", 8))
        self.assertEqual((shift["almuerzo"], shift["cena"], shift["guardia"]), (1, 1, 1))

    def test_assignments_support_colored_reminders(self):
        with closing(database.connect()) as conn:
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(asignaciones)")}
        self.assertTrue({"color", "nota"}.issubset(columns))

    def test_update_versions_follow_semantic_order(self):
        self.assertTrue(is_newer("v0.2.0", "0.2.0-beta.1"))
        self.assertTrue(is_newer("v0.2.0-beta.2", "0.2.0-beta.1"))
        self.assertFalse(is_newer("v0.1.9", "0.2.0-beta.1"))
        self.assertIsNone(version_key("una-version-invalida"))

    def test_update_package_is_verified_and_staged(self):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as package:
            package.writestr("CuadrantO.exe", b"portable-nuevo")
        payload = archive.getvalue()
        info = UpdateInfo(
            version="9.0.0", tag="v9.0.0", title="Prueba", notes="", page_url="",
            asset_name="CuadrantO-portable-9.0.0-windows-x64.zip", download_url="https://example.invalid/update.zip",
            digest="sha256:" + hashlib.sha256(payload).hexdigest(),
        )
        folder = Path(__file__).parent / "_updater_test"
        update_folder = folder / ".updates"
        if update_folder.exists():
            shutil.rmtree(update_folder)
        with patch.object(updater, "APP_DIR", folder), \
                patch.object(updater.sys, "frozen", True, create=True), \
                patch.object(updater.sys, "platform", "win32"), \
                patch.object(updater.urllib.request, "urlopen", return_value=io.BytesIO(payload)), \
                patch.object(updater, "create_database_backup") as backup:
            target = updater.download_and_stage(info)
            self.assertEqual(target.read_bytes(), b"portable-nuevo")
            backup.assert_called_once_with(reason="antes_actualizar")
        shutil.rmtree(update_folder)


if __name__ == "__main__":
    unittest.main()
