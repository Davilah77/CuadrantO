from datetime import date, datetime, timedelta
from tkinter import messagebox

import customtkinter as ctk

from core.database import connect, transaction
from core.settings import load_settings
from core.window_state import remember_window


DAYS = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")
SPECIAL_VALUES = ("", "DESCANSO", "PROPIO", "BAJA", "FALTA")
VALUE_COLORS = {
    "DESCANSO": ("#2E8B57", "#257346"),
    "PROPIO": ("#7D3C98", "#6C3483"),
    "BAJA": ("#C0392B", "#A93226"),
    "FALTA": ("#E67E22", "#CA6F1E"),
}
REMINDER_COLORS = {
    "Amarillo": ("#E0A800", "#9A7300"),
    "Naranja": ("#E67E22", "#CA6F1E"),
    "Morado": ("#8E44AD", "#71368A"),
    "Rosa": ("#D65A8B", "#A83E68"),
    "Azul": ("#2471A3", "#1B4F72"),
    "Verde": ("#2E8B57", "#257346"),
    "Turquesa": ("#159E9C", "#117A78"),
    "Rojo": ("#C0392B", "#A93226"),
    "Gris": ("#707B7C", "#566263"),
}
COVERAGE_COLORS = {
    "red": ("#FFB3AD", "#8B2D25"),
    "yellow": ("#FFE58A", "#806C13"),
    "green": ("#A9DF9C", "#276738"),
    "purple": ("#D7B5E8", "#66347A"),
}
TABLE_SURFACE = ("gray86", "gray17")


def parse_week(value: str) -> date:
    value = value.strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            selected = datetime.strptime(value, fmt).date()
            return selected - timedelta(days=selected.weekday())
        except ValueError:
            pass
    raise ValueError("Escribe una fecha válida, por ejemplo 21/09/2026.")


def build_cuadrante(parent, app):
    parent._controller = ScheduleModule(parent, app)


class ScheduleModule:
    def __init__(self, parent, app):
        self.parent = parent
        self.app = app
        self.assignment_vars = {}
        self.assignment_widgets = {}
        self.reminder_buttons = {}
        self.reminders = {}
        self.client_vars = {}
        self.coverage_labels = {}
        self.opening_labels = {}
        self.guard_labels = {}
        self.ett_hour_vars = {}
        self.ett_hour_widgets = {}
        self.ett_targets = {}
        self._build()
        self.load_week()

    def _build(self):
        toolbar = ctk.CTkFrame(self.parent)
        toolbar.pack(fill="x", padx=10, pady=(10, 5))
        ctk.CTkLabel(toolbar, text="Cuadrante semanal", font=ctk.CTkFont(size=19, weight="bold")).pack(side="left", padx=15, pady=12)
        self.week_var = ctk.StringVar(value=date.today().strftime("%d/%m/%Y"))
        ctk.CTkEntry(toolbar, textvariable=self.week_var, width=130).pack(side="left", padx=5)
        ctk.CTkButton(toolbar, text="Cargar semana", width=115, command=self.load_week).pack(side="left", padx=4)
        ctk.CTkButton(toolbar, text="Turnos", width=82, command=self.app.open_shift_manager).pack(side="right", padx=(4, 14))
        ctk.CTkButton(toolbar, text="Empleados", width=92, command=self.app.open_employee_manager).pack(side="right", padx=4)
        ctk.CTkButton(toolbar, text="Exportar PDF", width=105, command=self.export_pdf).pack(side="right", padx=4)
        ctk.CTkButton(toolbar, text="Guardar", width=95, command=self.save).pack(side="right", padx=4)

        self.week_title = ctk.CTkLabel(self.parent, text="", font=ctk.CTkFont(size=15, weight="bold"))
        self.week_title.pack(pady=(2, 5))
        self.scroll = ctk.CTkScrollableFrame(self.parent, fg_color=TABLE_SURFACE)
        self.scroll.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.grid = ctk.CTkFrame(self.scroll, fg_color=TABLE_SURFACE)
        self.grid.pack(fill="x")
        self._render_grid()

    def _load_catalogues(self):
        with connect() as conn:
            self.employees = conn.execute(
                "SELECT id,categoria,nombre FROM empleados WHERE activo=1 ORDER BY orden,nombre"
            ).fetchall()
            shift_rows = conn.execute(
                "SELECT * FROM turnos WHERE activo=1 ORDER BY orden,codigo"
            ).fetchall()
        self.shifts = {row["codigo"]: dict(row) for row in shift_rows}
        self.options = list(SPECIAL_VALUES) + list(self.shifts)

    def _render_grid(self):
        for child in self.grid.winfo_children():
            child.destroy()
        self.assignment_vars.clear()
        self.assignment_widgets.clear()
        self.reminder_buttons.clear()
        self.client_vars.clear()
        self.coverage_labels.clear()
        self.opening_labels.clear()
        self.guard_labels.clear()
        self.ett_hour_vars.clear()
        self.ett_hour_widgets.clear()
        self._load_catalogues()
        self.grid.grid_columnconfigure(0, weight=1)
        for column in range(1, 8):
            self.grid.grid_columnconfigure(column, minsize=122, weight=0)
        ctk.CTkLabel(self.grid, text="Empleado", width=235, anchor="w", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, padx=2, pady=4, sticky="ew")
        for day_index, day in enumerate(DAYS):
            ctk.CTkLabel(self.grid, text=day, width=120, font=ctk.CTkFont(weight="bold")).grid(row=0, column=day_index + 1, padx=2, pady=4)
        row_index = 1
        current_category = None
        for employee in self.employees:
            if employee["categoria"] != current_category:
                current_category = employee["categoria"]
                ctk.CTkLabel(
                    self.grid, text=current_category, anchor="w", font=ctk.CTkFont(weight="bold"),
                    fg_color=("#F4E84A", "#756D10"), text_color=("#111111", "white"), corner_radius=4,
                ).grid(row=row_index, column=0, columnspan=8, padx=2, pady=(7, 2), sticky="ew")
                row_index += 1
            if employee["categoria"] == "ETT":
                employee_cell = ctk.CTkFrame(self.grid, width=235, height=28, fg_color=TABLE_SURFACE)
                employee_cell.grid(row=row_index, column=0, padx=3, pady=2, sticky="ew")
                employee_cell.grid_propagate(False)
                ctk.CTkLabel(employee_cell, text=employee["nombre"], anchor="w", font=ctk.CTkFont(weight="bold")).pack(side="left", fill="x", expand=True)
                employee_id = employee["id"]
                self.ett_targets.setdefault(employee_id, 40)
                hour_var = ctk.StringVar(value="0/40 h")
                hour_menu = ctk.CTkOptionMenu(
                    employee_cell, values=[f"{hours} h" for hours in range(0, 61)], variable=hour_var,
                    width=72, height=25, font=ctk.CTkFont(size=10, weight="bold"),
                    dropdown_font=ctk.CTkFont(size=11),
                    command=lambda value, emp=employee_id: self._ett_target_changed(emp, value),
                )
                hour_menu.pack(side="right", padx=(4, 0))
                self.ett_hour_vars[employee_id] = hour_var
                self.ett_hour_widgets[employee_id] = hour_menu
            else:
                ctk.CTkLabel(self.grid, text=employee["nombre"], width=235, anchor="w", font=ctk.CTkFont(weight="bold")).grid(row=row_index, column=0, padx=3, pady=2, sticky="ew")
            for day_index in range(7):
                variable = ctk.StringVar(value="")
                cell = ctk.CTkFrame(self.grid, width=120, height=28, fg_color=TABLE_SURFACE)
                cell.grid(row=row_index, column=day_index + 1, padx=2, pady=2)
                cell.grid_propagate(False)
                cell.pack_propagate(False)
                widget = ctk.CTkOptionMenu(
                    cell, values=self.options, variable=variable, width=92, height=28,
                    font=ctk.CTkFont(size=11), dropdown_font=ctk.CTkFont(size=11, weight="bold"),
                    command=lambda value, emp=employee["id"], day=day_index: self._assignment_changed(emp, day, value),
                )
                widget.pack(side="left")
                reminder = ctk.CTkButton(
                    cell, text="●", width=25, height=28, fg_color=("#AEB5BA", "#4E555A"),
                    hover_color=("#8F989E", "#646B70"),
                    command=lambda emp=employee["id"], day=day_index: self.open_reminder(emp, day),
                )
                reminder.pack(side="left", padx=(3, 0))
                self.assignment_vars[(employee["id"], day_index)] = variable
                self.assignment_widgets[(employee["id"], day_index)] = widget
                self.reminder_buttons[(employee["id"], day_index)] = reminder
            row_index += 1

        row_index += 1
        ctk.CTkLabel(self.grid, text="Clientes en servicio", anchor="w", font=ctk.CTkFont(weight="bold"), fg_color=("#F4E84A", "#756D10"), text_color=("#111111", "white"), corner_radius=4).grid(row=row_index, column=0, columnspan=8, sticky="ew", pady=(4, 2))
        row_index += 1
        for service in ("desayuno", "almuerzo", "cena", "todo_incluido"):
            ctk.CTkLabel(self.grid, text=service.replace("_", " ").title(), anchor="w", font=ctk.CTkFont(weight="bold")).grid(row=row_index, column=0, padx=3, pady=2, sticky="ew")
            for day_index in range(7):
                variable = ctk.StringVar(value="0")
                ctk.CTkEntry(self.grid, textvariable=variable, width=120, justify="center", font=ctk.CTkFont(weight="bold")).grid(row=row_index, column=day_index + 1, padx=2, pady=2)
                self.client_vars[(service, day_index)] = variable
            row_index += 1

        ctk.CTkLabel(self.grid, text="Trabajadores en servicio", anchor="w", font=ctk.CTkFont(weight="bold"), fg_color=("#F4E84A", "#756D10"), text_color=("#111111", "white"), corner_radius=4).grid(row=row_index, column=0, columnspan=8, sticky="ew", pady=(8, 2))
        row_index += 1
        for service in ("desayuno", "almuerzo", "cena"):
            ctk.CTkLabel(self.grid, text=service.title(), anchor="w").grid(row=row_index, column=0, padx=3, pady=2, sticky="ew")
            for day_index in range(7):
                label = ctk.CTkLabel(self.grid, text="0", width=120, corner_radius=5, font=ctk.CTkFont(weight="bold"))
                label.grid(row=row_index, column=day_index + 1, padx=2, pady=2)
                self.coverage_labels[(service, day_index)] = label
            row_index += 1

        ctk.CTkLabel(self.grid, text="Apertura", anchor="w", font=ctk.CTkFont(weight="bold"), fg_color=("#B8E33D", "#466819"), corner_radius=4).grid(row=row_index, column=0, padx=3, pady=4, sticky="ew")
        for day_index in range(7):
            label = ctk.CTkLabel(self.grid, text="—", width=120, corner_radius=5, fg_color=("#D9F09B", "#345019"), wraplength=115)
            label.grid(row=row_index, column=day_index + 1, padx=2, pady=4)
            self.opening_labels[day_index] = label
        row_index += 1
        ctk.CTkLabel(self.grid, text="Guardia", anchor="w", font=ctk.CTkFont(weight="bold"), fg_color=("#B9D7EA", "#1F4E68"), corner_radius=4).grid(row=row_index, column=0, padx=3, pady=4, sticky="ew")
        for day_index in range(7):
            label = ctk.CTkLabel(self.grid, text="—", width=120, corner_radius=5, fg_color=("#D7EBF7", "#245B78"), wraplength=115)
            label.grid(row=row_index, column=day_index + 1, padx=2, pady=4)
            self.guard_labels[day_index] = label
        row_index += 1
        self.reminder_summary = ctk.CTkLabel(
            self.grid, text="Sin recordatorios especiales esta semana.", anchor="w",
            justify="left", wraplength=1050, fg_color=("#FFF3CD", "#55450D"),
            corner_radius=5,
        )
        self.reminder_summary.grid(row=row_index, column=0, columnspan=8, sticky="ew", padx=3, pady=(8, 4), ipady=5)
        self._apply_theme_surfaces(self.grid)

    def _apply_theme_surfaces(self, widget):
        for child in widget.winfo_children():
            if isinstance(child, ctk.CTkLabel) and child.cget("fg_color") == "transparent":
                child.configure(fg_color=TABLE_SURFACE)
            self._apply_theme_surfaces(child)

    def refresh_catalogues(self):
        preserved = {(key): variable.get() for key, variable in self.assignment_vars.items()}
        clients = {(key): variable.get() for key, variable in self.client_vars.items()}
        self._render_grid()
        self.reminders = {key: value for key, value in self.reminders.items() if key in self.assignment_vars}
        for key, value in preserved.items():
            if key in self.assignment_vars and value in self.options:
                self.assignment_vars[key].set(value)
                self._paint_assignment(key, value)
        for key, value in clients.items():
            if key in self.client_vars:
                self.client_vars[key].set(value)
        self.recalculate()

    def _assignment_changed(self, employee_id, day_index, value):
        if value not in self.shifts:
            self.reminders.pop((employee_id, day_index), None)
        self._paint_assignment((employee_id, day_index), value)
        self.recalculate()

    def _ett_target_changed(self, employee_id, value):
        try:
            self.ett_targets[employee_id] = int(value.split()[0])
        except (ValueError, IndexError):
            return
        self.recalculate()

    @staticmethod
    def _hours_text(value):
        return str(int(value)) if float(value).is_integer() else f"{value:.1f}".replace(".", ",")

    def _refresh_ett_hours(self):
        for employee_id, variable in self.ett_hour_vars.items():
            assigned = 0.0
            for day_index in range(7):
                shift = self.shifts.get(self.assignment_vars[(employee_id, day_index)].get())
                if shift:
                    assigned += float(shift["horas"])
            target = self.ett_targets.get(employee_id, 40)
            variable.set(f"{self._hours_text(assigned)}/{target} h")
            if target == 0:
                color = ("#707B7C", "#566263")
            elif assigned == target:
                color = ("#2E8B57", "#257346")
            elif assigned > target:
                color = ("#C0392B", "#A93226")
            else:
                color = ("#E67E22", "#CA6F1E")
            self.ett_hour_widgets[employee_id].configure(fg_color=color, button_color=color)

    def _paint_assignment(self, key, value):
        widget = self.assignment_widgets[key]
        if value in self.shifts:
            widget.configure(font=ctk.CTkFont(size=12, weight="bold"))
        elif value:
            widget.configure(font=ctk.CTkFont(size=10, weight="bold"))
        else:
            widget.configure(font=ctk.CTkFont(size=11))
        reminder = self.reminders.get(key)
        color = REMINDER_COLORS.get(reminder["color"]) if reminder else VALUE_COLORS.get(value)
        if color:
            widget.configure(fg_color=color, button_color=color, text_color="white")
        elif not value:
            widget.configure(
                fg_color=("#F9F9FA", "#159DB5"), button_color=("#D5D9DC", "#0D7185"),
                text_color=("gray10", "white"),
            )
        else:
            widget.configure(fg_color=("#3B8ED0", "#159DB5"), button_color=("#36719F", "#0D7185"), text_color=("white", "white"))
        button = self.reminder_buttons[key]
        if reminder:
            button.configure(fg_color=color, hover_color=color, text="!")
        else:
            button.configure(fg_color=("#AEB5BA", "#4E555A"), hover_color=("#8F989E", "#646B70"), text="●")

    def open_reminder(self, employee_id, day_index):
        value = self.assignment_vars[(employee_id, day_index)].get()
        if value not in self.shifts:
            messagebox.showinfo("Recordatorio", "Primero asigna un turno de trabajo a esta casilla.", parent=self.parent)
            return
        employee = next(row for row in self.employees if row["id"] == employee_id)
        current = self.reminders.get((employee_id, day_index), {"color": "Amarillo", "nota": ""})
        dialog = ctk.CTkToplevel(self.parent)
        dialog.title("Recordatorio especial")
        remember_window(dialog, "shift_reminder", "540x340")
        dialog.transient(self.parent.winfo_toplevel())
        dialog.grab_set()
        ctk.CTkLabel(
            dialog, text=f'{employee["nombre"]} · {DAYS[day_index]} · {value}',
            font=ctk.CTkFont(size=17, weight="bold"),
        ).pack(pady=(20, 12))
        ctk.CTkLabel(dialog, text="Color del aviso").pack(anchor="w", padx=24)
        color_var = ctk.StringVar(value=current["color"])
        ctk.CTkOptionMenu(dialog, values=list(REMINDER_COLORS), variable=color_var).pack(fill="x", padx=24, pady=(3, 12))
        ctk.CTkLabel(dialog, text="Motivo o nota").pack(anchor="w", padx=24)
        note = ctk.CTkTextbox(dialog, height=90)
        note.pack(fill="x", padx=24, pady=(3, 14))
        note.insert("1.0", current["nota"])
        actions = ctk.CTkFrame(dialog, fg_color="transparent")
        actions.pack(fill="x", padx=24)

        def save_reminder():
            self.reminders[(employee_id, day_index)] = {"color": color_var.get(), "nota": note.get("1.0", "end").strip()}
            self._paint_assignment((employee_id, day_index), value)
            self.recalculate()
            dialog.destroy()

        def clear_reminder():
            self.reminders.pop((employee_id, day_index), None)
            self._paint_assignment((employee_id, day_index), value)
            self.recalculate()
            dialog.destroy()

        ctk.CTkButton(actions, text="Quitar aviso", fg_color="#8B3A3A", command=clear_reminder).pack(side="left")
        ctk.CTkButton(actions, text="Guardar aviso", command=save_reminder).pack(side="right")

    def _dates(self):
        monday = parse_week(self.week_var.get())
        return monday, [(monday + timedelta(days=index)).isoformat() for index in range(7)]

    def load_week(self):
        try:
            monday, dates = self._dates()
            self.week_var.set(monday.strftime("%d/%m/%Y"))
            self.week_title.configure(text=f"Semana del {monday:%d/%m/%Y} al {(monday + timedelta(days=6)):%d/%m/%Y}")
            with connect() as conn:
                assignment_rows = conn.execute(
                    "SELECT empleado_id,fecha,valor,color,nota FROM asignaciones WHERE fecha BETWEEN ? AND ?", (dates[0], dates[-1])
                ).fetchall()
                assignments = {(row["empleado_id"], row["fecha"]): row["valor"] for row in assignment_rows}
                saved_reminders = {(row["empleado_id"], row["fecha"]): {"color": row["color"], "nota": row["nota"]} for row in assignment_rows if row["color"]}
                clients = {row["fecha"]: row for row in conn.execute(
                    "SELECT * FROM clientes WHERE fecha BETWEEN ? AND ?", (dates[0], dates[-1])
                )}
                ett_targets = {
                    row["empleado_id"]: row["horas_objetivo"] for row in conn.execute(
                        "SELECT empleado_id,horas_objetivo FROM ett_horas_semana WHERE semana=?", (dates[0],)
                    )
                }
            self.ett_targets = {employee_id: int(ett_targets.get(employee_id, 40)) for employee_id in self.ett_hour_vars}
            self.reminders.clear()
            for (employee_id, day_index), variable in self.assignment_vars.items():
                value = assignments.get((employee_id, dates[day_index]), "")
                variable.set(value if value in self.options else "")
                reminder = saved_reminders.get((employee_id, dates[day_index]))
                if reminder:
                    self.reminders[(employee_id, day_index)] = reminder
                self._paint_assignment((employee_id, day_index), variable.get())
            for (service, day_index), variable in self.client_vars.items():
                row = clients.get(dates[day_index])
                variable.set(str(row[service] if row else 0))
            self.recalculate()
        except Exception as exc:
            messagebox.showerror("No se pudo cargar", str(exc), parent=self.parent)

    def recalculate(self):
        settings = load_settings()
        employee_names = {row["id"]: row["nombre"] for row in self.employees}
        for day_index in range(7):
            counts = {service: 0 for service in ("desayuno", "almuerzo", "cena")}
            openings = []
            guards = []
            for employee in self.employees:
                value = self.assignment_vars[(employee["id"], day_index)].get()
                shift = self.shifts.get(value)
                if not shift:
                    continue
                for service in counts:
                    counts[service] += int(bool(shift[service]))
                if shift["apertura"]:
                    openings.append(employee_names[employee["id"]])
                if shift.get("guardia"):
                    guards.append(employee_names[employee["id"]])
            for service, count in counts.items():
                limits = settings["coverage"][service]
                if count >= int(limits["purple"]):
                    color = "purple"
                elif count >= int(limits["green"]):
                    color = "green"
                elif count >= int(limits["yellow"]):
                    color = "yellow"
                else:
                    color = "red"
                self.coverage_labels[(service, day_index)].configure(text=str(count), fg_color=COVERAGE_COLORS[color])
            opening_label = self.opening_labels[day_index]
            if len(openings) > 1:
                opening_label.configure(text="DUPLICADO: " + " / ".join(openings), fg_color=VALUE_COLORS["FALTA"], text_color="white")
            elif openings:
                opening_label.configure(text=openings[0], fg_color=("#D9F09B", "#345019"), text_color=("gray10", "white"))
            else:
                opening_label.configure(text="SIN APERTURA", fg_color=("#FFD2B3", "#713B18"), text_color=("gray10", "white"))
            guard_label = self.guard_labels[day_index]
            if len(guards) > 1:
                guard_label.configure(text="DUPLICADO: " + " / ".join(guards), fg_color=VALUE_COLORS["FALTA"], text_color="white")
            elif guards:
                guard_label.configure(text=guards[0], fg_color=("#D7EBF7", "#245B78"), text_color=("gray10", "white"))
            else:
                guard_label.configure(text="SIN GUARDIA", fg_color=("#FFD2B3", "#713B18"), text_color=("gray10", "white"))
        self._refresh_ett_hours()
        employee_names = {row["id"]: row["nombre"] for row in self.employees}
        reminder_lines = []
        for (employee_id, day_index), reminder in sorted(self.reminders.items(), key=lambda item: (item[0][1], item[0][0])):
            note = reminder["nota"] or "Sin detalle"
            reminder_lines.append(f'{DAYS[day_index]} · {employee_names[employee_id]}: {note}')
        self.reminder_summary.configure(
            text="Recordatorios: " + "   |   ".join(reminder_lines) if reminder_lines else "Sin recordatorios especiales esta semana."
        )

    def save(self):
        try:
            monday, dates = self._dates()
            assignments = []
            for (employee_id, day_index), variable in self.assignment_vars.items():
                value = variable.get().strip()
                if value:
                    reminder = self.reminders.get((employee_id, day_index), {"color": "", "nota": ""})
                    assignments.append((dates[day_index], employee_id, value, reminder["color"], reminder["nota"]))
            clients = []
            for day_index, current_date in enumerate(dates):
                numbers = []
                for service in ("desayuno", "almuerzo", "cena", "todo_incluido"):
                    raw = self.client_vars[(service, day_index)].get().strip() or "0"
                    number = int(raw)
                    if number < 0:
                        raise ValueError("Los clientes no pueden ser negativos.")
                    numbers.append(number)
                clients.append((current_date, *numbers))
            with transaction() as conn:
                conn.execute("DELETE FROM asignaciones WHERE fecha BETWEEN ? AND ?", (dates[0], dates[-1]))
                conn.executemany("INSERT INTO asignaciones(fecha,empleado_id,valor,color,nota) VALUES (?,?,?,?,?)", assignments)
                conn.executemany("""INSERT INTO clientes(fecha,desayuno,almuerzo,cena,todo_incluido)
                    VALUES (?,?,?,?,?) ON CONFLICT(fecha) DO UPDATE SET desayuno=excluded.desayuno,
                    almuerzo=excluded.almuerzo,cena=excluded.cena,todo_incluido=excluded.todo_incluido""", clients)
                conn.execute("DELETE FROM ett_horas_semana WHERE semana=?", (dates[0],))
                conn.executemany(
                    "INSERT INTO ett_horas_semana(semana,empleado_id,horas_objetivo) VALUES (?,?,?)",
                    [(dates[0], employee_id, self.ett_targets.get(employee_id, 40)) for employee_id in self.ett_hour_vars],
                )
            self.recalculate()
            duplicates = [DAYS[index] for index, label in self.opening_labels.items() if label.cget("text").startswith("DUPLICADO")]
            warning = f"\n\nRevisa aperturas duplicadas: {', '.join(duplicates)}." if duplicates else ""
            messagebox.showinfo("Cuadrante", f"Semana guardada correctamente.{warning}", parent=self.parent)
        except (ValueError, TypeError) as exc:
            messagebox.showerror("Datos incorrectos", str(exc), parent=self.parent)
        except Exception as exc:
            messagebox.showerror("No se pudo guardar", str(exc), parent=self.parent)

    def export_pdf(self):
        try:
            from reports import export_schedule_pdf
            monday, _dates = self._dates()
            path = export_schedule_pdf(self, monday)
            messagebox.showinfo("Informe creado", f"Se ha creado:\n\n{path}", parent=self.parent)
        except Exception as exc:
            messagebox.showerror("No se pudo exportar", str(exc), parent=self.parent)
