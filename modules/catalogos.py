from tkinter import messagebox

import customtkinter as ctk

from core.database import connect, transaction
from core.window_state import remember_window


CATEGORIES = ("MAITRE", "JEFES DE SECTOR", "CAMAREROS", "ETT")


def employee_manager(app, on_change):
    window = ctk.CTkToplevel(app)
    window.title("Gestionar empleados")
    remember_window(window, "employees", "760x620")
    window.transient(app)
    window.grab_set()
    listing = ctk.CTkScrollableFrame(window)
    listing.pack(fill="both", expand=True, padx=18, pady=(18, 8))
    listing.grid_columnconfigure(1, weight=1)

    def refresh():
        for child in listing.winfo_children():
            child.destroy()
        with connect() as conn:
            rows = conn.execute("SELECT id,categoria,nombre FROM empleados WHERE activo=1 ORDER BY orden,nombre").fetchall()
        for col, text in enumerate(("Categoría", "Empleado", "")):
            ctk.CTkLabel(listing, text=text, font=ctk.CTkFont(weight="bold"), anchor="w").grid(row=0, column=col, sticky="ew", padx=5, pady=5)
        for index, row in enumerate(rows, start=1):
            ctk.CTkLabel(listing, text=row["categoria"], width=155, anchor="w").grid(row=index, column=0, padx=5, pady=3)
            ctk.CTkLabel(listing, text=row["nombre"], anchor="w").grid(row=index, column=1, padx=5, pady=3, sticky="ew")
            actions = ctk.CTkFrame(listing, fg_color="transparent")
            actions.grid(row=index, column=2, padx=4)
            ctk.CTkButton(actions, text="Editar", width=60, command=lambda employee_id=row["id"]: edit(employee_id)).pack(side="left", padx=2)
            ctk.CTkButton(actions, text="×", width=34, fg_color="#B33A3A", command=lambda employee_id=row["id"], name=row["nombre"]: remove(employee_id, name)).pack(side="left", padx=2)

    def edit(employee_id=None):
        with connect() as conn:
            row = conn.execute("SELECT categoria,nombre FROM empleados WHERE id=?", (employee_id,)).fetchone() if employee_id else None
        dialog = ctk.CTkToplevel(window)
        dialog.title("Modificar empleado" if row else "Añadir empleado")
        remember_window(dialog, "employee_editor", "460x260")
        dialog.transient(window)
        dialog.grab_set()
        category = ctk.StringVar(value=row["categoria"] if row else CATEGORIES[-1])
        name = ctk.StringVar(value=row["nombre"] if row else "")
        ctk.CTkLabel(dialog, text="Categoría").pack(anchor="w", padx=24, pady=(20, 4))
        ctk.CTkOptionMenu(dialog, values=list(CATEGORIES), variable=category).pack(fill="x", padx=24)
        ctk.CTkLabel(dialog, text="Nombre").pack(anchor="w", padx=24, pady=(14, 4))
        ctk.CTkEntry(dialog, textvariable=name).pack(fill="x", padx=24)

        def save():
            clean = name.get().strip()
            if not clean:
                messagebox.showerror("Empleado", "Escribe el nombre.", parent=dialog)
                return
            with transaction() as conn:
                if employee_id:
                    conn.execute("UPDATE empleados SET categoria=?,nombre=? WHERE id=?", (category.get(), clean, employee_id))
                else:
                    order = conn.execute("SELECT COALESCE(MAX(orden),0)+1 FROM empleados").fetchone()[0]
                    conn.execute("INSERT INTO empleados(categoria,nombre,orden) VALUES (?,?,?)", (category.get(), clean, order))
            dialog.destroy()
            refresh()
            on_change()

        ctk.CTkButton(dialog, text="Guardar", command=save).pack(fill="x", padx=24, pady=22)

    def remove(employee_id, name):
        if not messagebox.askyesno("Empleado", f"¿Quitar a «{name}» de los cuadrantes futuros?", parent=window):
            return
        with transaction() as conn:
            conn.execute("UPDATE empleados SET activo=0 WHERE id=?", (employee_id,))
        refresh()
        on_change()

    ctk.CTkButton(window, text="Añadir empleado", command=edit).pack(fill="x", padx=18, pady=(0, 16))
    refresh()


def shift_manager(app, on_change):
    window = ctk.CTkToplevel(app)
    window.title("Gestionar turnos")
    remember_window(window, "shifts", "1050x680")
    window.transient(app)
    window.grab_set()
    listing = ctk.CTkScrollableFrame(window)
    listing.pack(fill="both", expand=True, padx=18, pady=(18, 8))
    listing.grid_columnconfigure(1, weight=1)

    def refresh():
        for child in listing.winfo_children():
            child.destroy()
        with connect() as conn:
            rows = conn.execute("SELECT * FROM turnos WHERE activo=1 ORDER BY orden,codigo").fetchall()
        headers = ("Código", "Mañana", "Tarde", "Horas", "Servicios", "Apertura", "")
        for col, text in enumerate(headers):
            ctk.CTkLabel(listing, text=text, font=ctk.CTkFont(weight="bold"), anchor="w").grid(row=0, column=col, sticky="ew", padx=4, pady=5)
        for index, row in enumerate(rows, start=1):
            services = ", ".join(name for name in ("desayuno", "almuerzo", "cena", "guardia") if row[name]) or "—"
            values = (row["codigo"], f'{row["entrada_manana"]}–{row["salida_manana"]}' if row["entrada_manana"] else "—", f'{row["entrada_tarde"]}–{row["salida_tarde"]}' if row["entrada_tarde"] else "—", str(row["horas"]), services, "Sí" if row["apertura"] else "No")
            for col, value in enumerate(values):
                ctk.CTkLabel(listing, text=value, anchor="w", width=(75 if col == 0 else 120)).grid(row=index, column=col, padx=4, pady=3, sticky="ew")
            actions = ctk.CTkFrame(listing, fg_color="transparent")
            actions.grid(row=index, column=6, padx=3)
            ctk.CTkButton(actions, text="Editar", width=60, command=lambda code=row["codigo"]: edit(code)).pack(side="left", padx=2)
            ctk.CTkButton(actions, text="×", width=34, fg_color="#B33A3A", command=lambda code=row["codigo"]: remove(code)).pack(side="left", padx=2)

    def edit(code=None):
        with connect() as conn:
            row = conn.execute("SELECT * FROM turnos WHERE codigo=?", (code,)).fetchone() if code else None
        dialog = ctk.CTkToplevel(window)
        dialog.title("Modificar turno" if row else "Añadir turno")
        remember_window(dialog, "shift_editor", "620x610")
        dialog.transient(window)
        dialog.grab_set()
        fields = {}
        defaults = {"codigo": "", "entrada_manana": "", "salida_manana": "", "entrada_tarde": "", "salida_tarde": "", "horas": "8"}
        for label, key in (("Código", "codigo"), ("Entrada mañana", "entrada_manana"), ("Salida mañana", "salida_manana"), ("Entrada tarde", "entrada_tarde"), ("Salida tarde", "salida_tarde"), ("Horas", "horas")):
            ctk.CTkLabel(dialog, text=label).pack(anchor="w", padx=24, pady=(8, 2))
            variable = ctk.StringVar(value=str(row[key]) if row else defaults[key])
            fields[key] = variable
            ctk.CTkEntry(dialog, textvariable=variable).pack(fill="x", padx=24)
        flags = {}
        flag_row = ctk.CTkFrame(dialog, fg_color="transparent")
        flag_row.pack(fill="x", padx=24, pady=14)
        for label, key in (("Desayuno", "desayuno"), ("Almuerzo", "almuerzo"), ("Cena", "cena"), ("Apertura", "apertura"), ("Guardia", "guardia")):
            variable = ctk.BooleanVar(value=bool(row[key]) if row else False)
            flags[key] = variable
            ctk.CTkCheckBox(flag_row, text=label, variable=variable).pack(side="left", padx=(0, 15))

        def save():
            new_code = fields["codigo"].get().strip().lower()
            if not new_code:
                messagebox.showerror("Turno", "El código es obligatorio.", parent=dialog)
                return
            try:
                hours = float(fields["horas"].get().replace(",", "."))
            except ValueError:
                messagebox.showerror("Turno", "Las horas deben ser numéricas.", parent=dialog)
                return
            values = [fields[key].get().strip() for key in ("entrada_manana", "salida_manana", "entrada_tarde", "salida_tarde")]
            with transaction() as conn:
                if code:
                    conn.execute("""UPDATE turnos SET codigo=?,entrada_manana=?,salida_manana=?,entrada_tarde=?,salida_tarde=?,horas=?,desayuno=?,almuerzo=?,cena=?,apertura=?,guardia=? WHERE codigo=?""", (new_code, *values, hours, *(int(flags[key].get()) for key in ("desayuno", "almuerzo", "cena", "apertura", "guardia")), code))
                else:
                    order = conn.execute("SELECT COALESCE(MAX(orden),0)+1 FROM turnos").fetchone()[0]
                    conn.execute("""INSERT INTO turnos(codigo,entrada_manana,salida_manana,entrada_tarde,salida_tarde,horas,desayuno,almuerzo,cena,apertura,guardia,orden) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", (new_code, *values, hours, *(int(flags[key].get()) for key in ("desayuno", "almuerzo", "cena", "apertura", "guardia")), order))
            dialog.destroy()
            refresh()
            on_change()

        ctk.CTkButton(dialog, text="Guardar turno", command=save).pack(fill="x", padx=24, pady=8)

    def remove(code):
        if not messagebox.askyesno("Turno", f"¿Desactivar el turno «{code}»?", parent=window):
            return
        with transaction() as conn:
            conn.execute("UPDATE turnos SET activo=0 WHERE codigo=?", (code,))
        refresh()
        on_change()

    ctk.CTkButton(window, text="Añadir turno", command=edit).pack(fill="x", padx=18, pady=(0, 16))
    refresh()
