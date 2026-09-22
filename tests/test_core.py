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
from core.window_state import _visible_geometry
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
        self.assertEqual(opening, {"d1", "dc1", "dc2", "dc3", "dc4"})

    def test_dac_covers_all_services_for_twelve_hours(self):
        with closing(database.connect()) as conn:
            shift = conn.execute("SELECT * FROM turnos WHERE codigo='dac'").fetchone()
        self.assertEqual(
            (shift["entrada_manana"], shift["salida_manana"], shift["entrada_tarde"], shift["salida_tarde"]),
            ("08:00", "16:00", "18:30", "22:30"),
        )
        self.assertEqual((shift["horas"], shift["desayuno"], shift["almuerzo"], shift["cena"]), (12, 1, 1, 1))

    def test_catalogue_migration_does_not_overwrite_later_customization(self):
        with database.transaction() as conn:
            conn.execute("UPDATE turnos SET apertura=1 WHERE codigo='dc5'")
            conn.execute("UPDATE turnos SET horas=11 WHERE codigo='dac'")
        database.initialize_database()
        with closing(database.connect()) as conn:
            dc5 = conn.execute("SELECT apertura FROM turnos WHERE codigo='dc5'").fetchone()[0]
            dac_hours = conn.execute("SELECT horas FROM turnos WHERE codigo='dac'").fetchone()[0]
        self.assertEqual((dc5, dac_hours), (1, 11))

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

    def test_saved_windows_are_kept_inside_the_visible_desktop(self):
        with patch("core.window_state._screen_bounds", return_value=(0, 0, 1920, 1080)):
            self.assertEqual(_visible_geometry(object(), "780x760+3000+2000"), "780x760+1840+1000")
            self.assertEqual(_visible_geometry(object(), "780x760-3000-2000"), "780x760-700+0")

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
