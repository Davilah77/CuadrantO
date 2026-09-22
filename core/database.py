import sqlite3
from contextlib import contextmanager
from datetime import datetime

from core.settings import configured_path


DEFAULT_EMPLOYEES = [
    ("MAITRE", "Maitre1", 10),
    ("JEFES DE SECTOR", "Jefe1", 20),
    ("JEFES DE SECTOR", "Jefe2", 21),
    ("CAMAREROS", "Camarero1", 30),
    ("CAMAREROS", "Camarero2", 31),
    ("CAMAREROS", "Camarero3", 32),
    ("CAMAREROS", "Camarero4", 33),
    ("CAMAREROS", "Camarero5", 34),
]

DEFAULT_SHIFTS = [
    ("d1", "06:30", "10:45", "", "", 4, 1, 0, 0, 1),
    ("d2", "07:00", "11:00", "", "", 4, 1, 0, 0, 0),
    ("d3", "08:00", "12:00", "", "", 4, 1, 0, 0, 0),
    ("d4", "09:00", "13:00", "", "", 4, 1, 0, 0, 0),
    ("da1", "08:00", "16:00", "", "", 8, 1, 1, 0, 0),
    ("da2", "08:30", "16:30", "", "", 8, 1, 1, 0, 0),
    ("da3", "09:00", "17:00", "", "", 8, 1, 1, 0, 0),
    ("dac", "08:00", "16:00", "18:30", "22:30", 12, 1, 1, 1, 0),
    ("dc1", "06:45", "10:45", "18:15", "22:15", 8, 1, 0, 1, 1),
    ("dc2", "06:45", "10:45", "18:45", "22:45", 8, 1, 0, 1, 1),
    ("dc3", "07:00", "11:00", "18:15", "22:15", 8, 1, 0, 1, 1),
    ("dc4", "07:00", "11:00", "18:45", "22:45", 8, 1, 0, 1, 1),
    ("dc5", "07:30", "11:30", "18:15", "22:15", 8, 1, 0, 1, 0),
    ("dc6", "07:30", "11:30", "18:45", "22:45", 8, 1, 0, 1, 0),
    ("dc7", "08:00", "12:00", "18:15", "22:15", 8, 1, 0, 1, 0),
    ("dc8", "08:00", "12:00", "18:45", "22:45", 8, 1, 0, 1, 0),
    ("dc9", "08:30", "12:30", "18:15", "22:15", 8, 1, 0, 1, 0),
    ("dc10", "08:30", "12:30", "18:45", "22:45", 8, 1, 0, 1, 0),
    ("dc11", "09:00", "13:00", "18:15", "22:15", 8, 1, 0, 1, 0),
    ("dc12", "09:00", "13:00", "18:45", "22:45", 8, 1, 0, 1, 0),
    ("ac1", "11:30", "15:30", "18:15", "22:15", 8, 0, 1, 1, 0),
    ("ac2", "11:30", "15:30", "18:45", "22:45", 8, 0, 1, 1, 0),
    ("ac3", "12:00", "16:00", "18:15", "22:15", 8, 0, 1, 1, 0),
    ("ac4", "12:00", "16:00", "18:45", "22:45", 8, 0, 1, 1, 0),
    ("ac5", "12:30", "16:30", "18:15", "22:15", 8, 0, 1, 1, 0),
    ("ac6", "12:30", "16:30", "18:45", "22:45", 8, 0, 1, 1, 0),
    ("a1", "11:30", "15:30", "", "", 4, 0, 1, 0, 0),
    ("a2", "12:00", "16:00", "", "", 4, 0, 1, 0, 0),
    ("a3", "12:30", "16:30", "", "", 4, 0, 1, 0, 0),
    ("c1", "", "", "18:15", "22:15", 4, 0, 0, 1, 0),
    ("c2", "", "", "18:45", "22:45", 4, 0, 0, 1, 0),
    ("g1", "", "", "14:00", "22:00", 8, 0, 1, 1, 0, 1),
]


def connect():
    path = configured_path("database_path")
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def transaction():
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def initialize_database() -> None:
    with transaction() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS empleados(
            id INTEGER PRIMARY KEY, categoria TEXT NOT NULL, nombre TEXT NOT NULL,
            orden INTEGER NOT NULL DEFAULT 0, activo INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS turnos(
            codigo TEXT PRIMARY KEY COLLATE NOCASE, entrada_manana TEXT, salida_manana TEXT,
            entrada_tarde TEXT, salida_tarde TEXT, horas REAL NOT NULL DEFAULT 0,
            desayuno INTEGER NOT NULL DEFAULT 0, almuerzo INTEGER NOT NULL DEFAULT 0,
            cena INTEGER NOT NULL DEFAULT 0, apertura INTEGER NOT NULL DEFAULT 0,
            guardia INTEGER NOT NULL DEFAULT 0,
            activo INTEGER NOT NULL DEFAULT 1, orden INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS asignaciones(
            fecha TEXT NOT NULL, empleado_id INTEGER NOT NULL, valor TEXT NOT NULL,
            color TEXT NOT NULL DEFAULT '', nota TEXT NOT NULL DEFAULT '',
            PRIMARY KEY(fecha,empleado_id), FOREIGN KEY(empleado_id) REFERENCES empleados(id)
        );
        CREATE TABLE IF NOT EXISTS clientes(
            fecha TEXT PRIMARY KEY, desayuno INTEGER NOT NULL DEFAULT 0,
            almuerzo INTEGER NOT NULL DEFAULT 0, cena INTEGER NOT NULL DEFAULT 0,
            todo_incluido INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS app_meta(
            clave TEXT PRIMARY KEY, valor TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS ett_horas_semana(
            semana TEXT NOT NULL, empleado_id INTEGER NOT NULL, horas_objetivo INTEGER NOT NULL DEFAULT 40,
            PRIMARY KEY(semana,empleado_id), FOREIGN KEY(empleado_id) REFERENCES empleados(id)
        );
        """)
        shift_columns = {row["name"] for row in conn.execute("PRAGMA table_info(turnos)")}
        if "guardia" not in shift_columns:
            conn.execute("ALTER TABLE turnos ADD COLUMN guardia INTEGER NOT NULL DEFAULT 0")
        assignment_columns = {row["name"] for row in conn.execute("PRAGMA table_info(asignaciones)")}
        if "color" not in assignment_columns:
            conn.execute("ALTER TABLE asignaciones ADD COLUMN color TEXT NOT NULL DEFAULT ''")
        if "nota" not in assignment_columns:
            conn.execute("ALTER TABLE asignaciones ADD COLUMN nota TEXT NOT NULL DEFAULT ''")
        if conn.execute("SELECT COUNT(*) FROM empleados").fetchone()[0] == 0:
            conn.executemany("INSERT INTO empleados(categoria,nombre,orden) VALUES (?,?,?)", DEFAULT_EMPLOYEES)
        if conn.execute("SELECT COUNT(*) FROM turnos").fetchone()[0] == 0:
            conn.executemany("""INSERT INTO turnos(
                codigo,entrada_manana,salida_manana,entrada_tarde,salida_tarde,horas,
                desayuno,almuerzo,cena,apertura,guardia,orden) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                [(*row[:10], row[10] if len(row) > 10 else 0, index) for index, row in enumerate(DEFAULT_SHIFTS)],
            )
        conn.execute(
            "UPDATE turnos SET entrada_tarde='14:00',salida_tarde='22:00',horas=8,almuerzo=1,cena=1,guardia=1 WHERE codigo='g1'"
        )
        migration = "catalogo_dac_aperturas_2026_09"
        if conn.execute("SELECT 1 FROM app_meta WHERE clave=?", (migration,)).fetchone() is None:
            dac = next(row for row in DEFAULT_SHIFTS if row[0] == "dac")
            order = conn.execute("SELECT COALESCE(MAX(orden),0)+1 FROM turnos").fetchone()[0]
            conn.execute(
                """INSERT OR IGNORE INTO turnos(
                    codigo,entrada_manana,salida_manana,entrada_tarde,salida_tarde,horas,
                    desayuno,almuerzo,cena,apertura,guardia,orden) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (*dac[:10], dac[10] if len(dac) > 10 else 0, order),
            )
            conn.execute("UPDATE turnos SET apertura=0 WHERE codigo IN ('dc5','dc6')")
            conn.execute("INSERT INTO app_meta(clave,valor) VALUES (?,?)", (migration, "aplicada"))
