from datetime import date, datetime, timedelta
import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox
from tkinter import ttk

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont, ImageTk

from core.database import connect, transaction
from core.settings import load_settings
from core.window_state import apply_native_titlebar, remember_window


DAYS = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")
SPECIAL_VALUES = ("", "DESCANSO", "PROPIO", "BAJA", "FALTA")
VALUE_COLORS = {
    "DESCANSO": ("#2E8B57", "#257346"), "PROPIO": ("#7D3C98", "#6C3483"),
    "BAJA": ("#C0392B", "#A93226"), "FALTA": ("#E67E22", "#CA6F1E"),
}
REMINDER_COLORS = {
    "Amarillo": ("#E0A800", "#9A7300"), "Naranja": ("#E67E22", "#CA6F1E"),
    "Morado": ("#8E44AD", "#71368A"), "Rosa": ("#D65A8B", "#A83E68"),
    "Azul": ("#2471A3", "#1B4F72"), "Verde": ("#2E8B57", "#257346"),
    "Turquesa": ("#159E9C", "#117A78"), "Rojo": ("#C0392B", "#A93226"),
    "Gris": ("#707B7C", "#566263"),
}
COVERAGE_COLORS = {
    "red": ("#FFB3AD", "#8B2D25"), "yellow": ("#FFE58A", "#806C13"),
    "green": ("#A9DF9C", "#276738"), "purple": ("#D7B5E8", "#66347A"),
}
TABLE_SURFACE = ("#DBDBDB", "#2B2B2B")


def parse_week(value: str) -> date:
    value = value.strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            selected = datetime.strptime(value, fmt).date()
            return selected - timedelta(days=selected.weekday())
        except ValueError:
            pass
    raise ValueError("Escribe una fecha válida, por ejemplo 21/09/2026.")


def automatic_workers_required(clients: int) -> int:
    """Return the agreed staffing ratio: 1–199=1, 200–299=2, etc."""
    clients = max(0, int(clients))
    return 0 if clients == 0 else max(1, clients // 100)


def category_counts_for_automatic_coverage(category: str, settings: dict) -> bool:
    options = settings.get("automatic_coverage", {})
    rules = {
        "MAITRE": "count_maitre",
        "SEGUNDO MAITRE": "count_second_maitre",
        "JEFES DE SECTOR": "count_sector_heads",
    }
    return bool(options.get(rules[category], True)) if category in rules else category in ("CAMAREROS", "ETT")


def coverage_legend(mode: str):
    if mode == "automatic":
        return (("red", "Faltan camareros"), ("green", "OK"), ("purple", "Exceso de camareros"))
    return (
        ("red", "Falta"), ("yellow", "Falta, pero se puede dar el servicio"),
        ("green", "OK"), ("purple", "Sobra"),
    )


def build_cuadrante(parent, app):
    parent._controller = ScheduleModule(parent, app)


class DisplayValue:
    """Label-compatible value object: reports can read it without a real widget."""

    def __init__(self, text="", **values):
        self.values = {"text": text, **values}

    def configure(self, **values):
        self.values.update(values)

    def cget(self, key):
        return self.values.get(key)


class ScheduleModule:
    MIN_NAME_WIDTH = 235
    MIN_DAY_WIDTH = 122
    MAX_DAY_WIDTH = 190
    MIN_TABLE_WIDTH = MIN_NAME_WIDTH + MIN_DAY_WIDTH * 7

    def __init__(self, parent, app):
        self.parent = parent
        self.app = app
        self.assignment_vars = {}
        self.reminders = {}
        self.client_vars = {}
        self.coverage_labels = {}
        self.opening_labels = {}
        self.guard_labels = {}
        self.ett_hour_vars = {}
        self.ett_targets = {}
        self.ett_hour_colors = {}
        self.rows = []
        self.assignment_menu = None
        self.ett_menu = None
        self._active_assignment_key = None
        self._active_ett_employee = None
        self._editor = None
        self._editor_item = None
        self._editor_previous = None
        self._table_image = None
        self._draw = None
        self._drawing_suspended = False
        self.name_width = self.MIN_NAME_WIDTH
        self.day_width = float(self.MIN_DAY_WIDTH)
        self.table_width = self.MIN_TABLE_WIDTH
        self._resize_job = None
        self._scrollbar_job = None
        self._coverage_mode = str(load_settings().get("coverage_mode", "manual"))
        self._hscroll_visible = True
        self._vscroll_visible = True
        self._create_shared_fonts()
        self._build()
        self.load_week()

    def _create_shared_fonts(self):
        scale = float(load_settings().get("font_scale", 1.0))
        size = lambda value: max(8, round(value * scale))
        self.font_normal = tkfont.Font(family="Segoe UI", size=size(10))
        self.font_bold = tkfont.Font(family="Segoe UI", size=size(10), weight="bold")
        self.font_heading = tkfont.Font(family="Segoe UI", size=size(11), weight="bold")
        self.font_shift = tkfont.Font(family="Segoe UI", size=size(12), weight="bold")
        self.font_special = tkfont.Font(family="Segoe UI", size=size(9), weight="bold")
        self.font_small = tkfont.Font(family="Segoe UI", size=size(9))
        regular_candidates = (
            r"C:\Windows\Fonts\segoeui.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        )
        bold_candidates = (
            r"C:\Windows\Fonts\segoeuib.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        )

        def image_font(candidates, font_size):
            for path in candidates:
                try:
                    return ImageFont.truetype(path, size(font_size))
                except OSError:
                    continue
            return ImageFont.load_default()

        self.image_font_normal = image_font(regular_candidates, size(10))
        self.image_font_bold = image_font(bold_candidates, size(10))
        self.image_font_name = image_font(bold_candidates, size(12))
        self.image_font_heading = image_font(bold_candidates, size(11))
        self.image_font_shift = image_font(bold_candidates, size(12))
        self.image_font_special = image_font(bold_candidates, size(9))
        self.image_font_small = image_font(regular_candidates, size(9))

    @staticmethod
    def _theme_color(value):
        if isinstance(value, (tuple, list)):
            return value[1] if ctk.get_appearance_mode().lower() == "dark" else value[0]
        return value

    def _build(self):
        self.toolbar = tk.Frame(self.parent, bg=self._theme_color(TABLE_SURFACE), bd=0, highlightthickness=0)
        self.toolbar.pack(fill="x", padx=10, pady=(10, 5))
        ctk.CTkLabel(self.toolbar, text="Cuadrante semanal", font=ctk.CTkFont(size=19, weight="bold")).pack(side="left", padx=15, pady=12)
        self.week_var = ctk.StringVar(value=date.today().strftime("%d/%m/%Y"))
        ctk.CTkEntry(self.toolbar, textvariable=self.week_var, width=130).pack(side="left", padx=5)
        ctk.CTkButton(self.toolbar, text="Guardar semana", width=120, command=self.save).pack(side="left", padx=4)
        ctk.CTkButton(self.toolbar, text="Ver semanas", width=105, command=self.open_saved_weeks).pack(side="left", padx=4)
        ctk.CTkButton(self.toolbar, text="Turnos", width=82, command=self.app.open_shift_manager).pack(side="right", padx=(4, 14))
        ctk.CTkButton(self.toolbar, text="Empleados", width=92, command=self.app.open_employee_manager).pack(side="right", padx=4)
        ctk.CTkButton(self.toolbar, text="Exportar PDF", width=105, command=self.export_pdf).pack(side="right", padx=4)
        self.week_title = ctk.CTkLabel(self.parent, text="", font=ctk.CTkFont(size=15, weight="bold"))
        self.week_title.pack(pady=(2, 5))

        self.canvas_frame = tk.Frame(self.parent, bg=self._theme_color(TABLE_SURFACE), bd=0, highlightthickness=0)
        self.canvas_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.canvas = tk.Canvas(self.canvas_frame, bd=0, highlightthickness=0, bg=self._theme_color(TABLE_SURFACE), takefocus=True)
        self.vscroll = tk.Scrollbar(self.canvas_frame, orient="vertical", command=self.canvas.yview)
        self.hscroll = tk.Scrollbar(self.canvas_frame, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=self.vscroll.set, xscrollcommand=self.hscroll.set)
        self.canvas_frame.grid_rowconfigure(0, weight=1)
        self.canvas_frame.grid_columnconfigure(0, weight=1)
        self.canvas.grid(row=0, column=0, sticky="nsew", padx=(3, 0), pady=(3, 0))
        self.vscroll.grid(row=0, column=1, sticky="ns", padx=(0, 3), pady=3)
        self.hscroll.grid(row=1, column=0, sticky="ew", padx=3, pady=(0, 3))
        self.canvas.bind("<Button-1>", self._on_canvas_click)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Shift-MouseWheel>", self._on_shift_mousewheel)
        self.canvas.bind("<Button-4>", lambda _event: self.canvas.yview_scroll(-3, "units"))
        self.canvas.bind("<Button-5>", lambda _event: self.canvas.yview_scroll(3, "units"))
        self._render_grid()

    def _load_catalogues(self):
        with connect() as conn:
            self.employees = conn.execute("""SELECT id,categoria,nombre FROM empleados WHERE activo=1 ORDER BY
                CASE categoria WHEN 'MAITRE' THEN 10 WHEN 'SEGUNDO MAITRE' THEN 20
                WHEN 'JEFES DE SECTOR' THEN 30 WHEN 'CAMAREROS' THEN 40 WHEN 'ETT' THEN 50 ELSE 60 END,
                orden,nombre""").fetchall()
            shift_rows = conn.execute("SELECT * FROM turnos WHERE activo=1 ORDER BY orden,codigo").fetchall()
        self.shifts = {row["codigo"]: dict(row) for row in shift_rows}
        self.options = list(SPECIAL_VALUES) + list(self.shifts)

    def _add_row(self, kind, height, **values):
        y0 = self.rows[-1]["y1"] if self.rows else 0
        self.rows.append({"kind": kind, "y0": y0, "y1": y0 + height, **values})

    def _render_grid(self):
        self._drawing_suspended = True
        self._close_editor(commit=True)
        self.assignment_vars.clear()
        self.client_vars.clear()
        self.coverage_labels.clear()
        self.opening_labels.clear()
        self.guard_labels.clear()
        self.ett_hour_vars.clear()
        self.ett_hour_colors.clear()
        self.rows.clear()
        self._load_catalogues()
        self._build_assignment_menu()
        self._build_ett_menu()

        self._add_row("header", 38)
        current_category = None
        for employee in self.employees:
            if employee["categoria"] != current_category:
                current_category = employee["categoria"]
                self._add_row("section", 34, title=current_category)
            employee_id = employee["id"]
            self._add_row("employee", 36, employee=employee)
            if employee["categoria"] == "ETT":
                self.ett_targets.setdefault(employee_id, 40)
                self.ett_hour_vars[employee_id] = ctk.StringVar(value="0/40 h")
            for day_index in range(7):
                self.assignment_vars[(employee_id, day_index)] = ctk.StringVar(value="")

        self._add_row("spacer", 14)
        self._add_row("section", 34, title="Clientes en servicio")
        for service in ("desayuno", "almuerzo", "cena", "todo_incluido"):
            self._add_row("client", 36, service=service)
            for day_index in range(7):
                self.client_vars[(service, day_index)] = ctk.StringVar(value="0")
        self._add_row("section", 38, title="Trabajadores en servicio")
        for service in ("desayuno", "almuerzo", "cena"):
            self._add_row("coverage", 36, service=service)
            for day_index in range(7):
                self.coverage_labels[(service, day_index)] = DisplayValue("0", fg_color=COVERAGE_COLORS["red"])
        self._add_row("opening", 40)
        self._add_row("guard", 40)
        for day_index in range(7):
            self.opening_labels[day_index] = DisplayValue("—", fg_color=("#D9F09B", "#345019"), text_color=("#111111", "white"))
            self.guard_labels[day_index] = DisplayValue("—", fg_color=("#D7EBF7", "#245B78"), text_color=("#111111", "white"))
        self.reminder_summary = DisplayValue("Sin recordatorios especiales esta semana.")
        self._add_row("reminders", 58)
        self.canvas.configure(scrollregion=(0, 0, self.table_width, self.rows[-1]["y1"] + 4))
        self._drawing_suspended = False
        self._redraw()

    def _new_menu(self, font):
        return tk.Menu(
            self.canvas, tearoff=False, font=font,
            bg=self._theme_color(("#F5F5F5", "#303030")), fg=self._theme_color(("#111111", "#F3F3F3")),
            activebackground=self._theme_color(("#3B8ED0", "#159DB5")), activeforeground="white", bd=1, relief="solid",
        )

    def _build_assignment_menu(self):
        if self.assignment_menu is not None:
            self.assignment_menu.destroy()
        self.assignment_menu = self._new_menu(self.font_shift)
        for value in self.options:
            self.assignment_menu.add_command(label=value or "Sin turno", command=lambda selected=value: self._choose_assignment(selected))

    def _build_ett_menu(self):
        if self.ett_menu is not None:
            self.ett_menu.destroy()
        self.ett_menu = self._new_menu(self.font_normal)
        for hours in range(61):
            self.ett_menu.add_command(label=f"{hours} h", command=lambda selected=hours: self._choose_ett_hours(selected))

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
        return "break"

    def _on_shift_mousewheel(self, event):
        self.canvas.xview_scroll(-1 if event.delta > 0 else 1, "units")
        return "break"

    def _row_at(self, y):
        return next((row for row in self.rows if row["y0"] <= y < row["y1"]), None)

    def _day_x(self, day_index):
        return round(self.name_width + day_index * self.day_width)

    def _on_canvas_configure(self, event):
        if event.width <= 1:
            return
        table_width = max(self.MIN_TABLE_WIDTH, int(event.width))
        day_width = min(self.MAX_DAY_WIDTH, max(self.MIN_DAY_WIDTH, (table_width - self.MIN_NAME_WIDTH) / 7))
        name_width = round(table_width - day_width * 7)
        if table_width == self.table_width and name_width == self.name_width:
            return
        self.table_width = table_width
        self.name_width = name_width
        self.day_width = day_width
        self.canvas.configure(scrollregion=(0, 0, self.table_width, self.rows[-1]["y1"] + 4))
        if self._resize_job is not None:
            self.canvas.after_cancel(self._resize_job)
        # Durante el arrastre conservamos la imagen actual; al detenerse se
        # reconstruye una sola vez, evitando el efecto de dibujar celda a celda.
        self._resize_job = self.canvas.after(70, self._finish_canvas_resize)

    def _finish_canvas_resize(self):
        self._resize_job = None
        self._close_editor(commit=True)
        self._redraw()

    def _schedule_scrollbar_update(self):
        if self._scrollbar_job is None:
            self._scrollbar_job = self.canvas.after_idle(self._update_scrollbars)

    def _update_scrollbars(self):
        self._scrollbar_job = None
        if not self.rows:
            return
        need_horizontal = self.table_width > self.canvas.winfo_width() + 1
        need_vertical = self.rows[-1]["y1"] + 4 > self.canvas.winfo_height() + 1
        changed = False
        if need_horizontal != self._hscroll_visible:
            self._hscroll_visible = need_horizontal
            (self.hscroll.grid if need_horizontal else self.hscroll.grid_remove)()
            if not need_horizontal:
                self.canvas.xview_moveto(0)
            changed = True
        if need_vertical != self._vscroll_visible:
            self._vscroll_visible = need_vertical
            (self.vscroll.grid if need_vertical else self.vscroll.grid_remove)()
            if not need_vertical:
                self.canvas.yview_moveto(0)
            changed = True
        if changed:
            self.canvas.after_idle(self._schedule_scrollbar_update)

    def _on_canvas_click(self, event):
        self._close_editor(commit=True)
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        row = self._row_at(y)
        if not row:
            return
        day_index = int((x - self.name_width) // self.day_width) if x >= self.name_width else -1
        if row["kind"] == "employee":
            employee = row["employee"]
            if 0 <= day_index < 7:
                key = (employee["id"], day_index)
                if x >= self._day_x(day_index + 1) - 28:
                    self.open_reminder(*key)
                else:
                    self._active_assignment_key = key
                    self.assignment_menu.tk_popup(event.x_root, event.y_root)
            elif employee["categoria"] == "ETT" and x >= self.name_width - 82:
                self._active_ett_employee = employee["id"]
                self.ett_menu.tk_popup(event.x_root, event.y_root)
        elif row["kind"] == "client" and 0 <= day_index < 7:
            self._edit_client(row, day_index)

    def _choose_assignment(self, value):
        key = self._active_assignment_key
        if key in self.assignment_vars:
            self.assignment_vars[key].set(value)
            self._assignment_changed(key[0], key[1], value)

    def _choose_ett_hours(self, hours):
        if self._active_ett_employee in self.ett_targets:
            self.ett_targets[self._active_ett_employee] = int(hours)
            self.recalculate()

    def _edit_client(self, row, day_index):
        variable = self.client_vars[(row["service"], day_index)]
        self._editor_previous = variable.get()
        x0, x1, y0 = self._day_x(day_index), self._day_x(day_index + 1), row["y0"]
        background = self._theme_color(("#F9F9FA", "#343638"))
        foreground = self._theme_color(("#111111", "#F3F3F3"))
        self._editor = tk.Entry(
            self.canvas, textvariable=variable, justify="center", font=self.font_bold, bd=1, relief="solid",
            bg=background, fg=foreground, insertbackground=foreground, selectbackground="#3B8ED0",
        )
        self._editor_item = self.canvas.create_window(
            x0 + 3, y0 + 3, width=x1 - x0 - 6, height=row["y1"] - y0 - 6, anchor="nw", window=self._editor,
        )
        self._editor.bind("<Return>", lambda _event: self._close_editor(commit=True))
        self._editor.bind("<Escape>", lambda _event: self._close_editor(commit=False))
        self._editor.bind("<FocusOut>", lambda _event: self._close_editor(commit=True))
        self._editor.focus_set()
        self._editor.select_range(0, "end")

    def _close_editor(self, commit=True):
        editor, item = self._editor, self._editor_item
        if editor is None:
            return
        variable_name = str(editor.cget("textvariable"))
        if not commit:
            try:
                editor.setvar(variable_name, self._editor_previous)
            except tk.TclError:
                pass
        self._editor = self._editor_item = self._editor_previous = None
        if item is not None:
            self.canvas.delete(item)
        editor.destroy()
        if commit:
            self.recalculate()
        else:
            self._redraw()

    def _cell(self, x0, y0, x1, y1, fill, text="", text_color=None, font=None, anchor="center"):
        fill = self._theme_color(fill)
        text_color = self._theme_color(text_color or ("#111111", "#F3F3F3"))
        self._draw.rounded_rectangle((x0 + 2, y0 + 2, x1 - 2, y1 - 2), radius=4, fill=fill)
        if text:
            tx, text_anchor = ((x0 + 8, "lm") if anchor == "w" else ((x0 + x1) / 2, "mm"))
            self._draw.text((tx, (y0 + y1) / 2), text=text, fill=text_color, font=font or self.image_font_normal, anchor=text_anchor)

    def _dropdown_arrow(self, x, y, color):
        color = self._theme_color(color)
        self._draw.polygon(((x - 4, y - 2), (x + 4, y - 2), (x, y + 3)), fill=color)

    def _assignment_style(self, key, value):
        reminder = self.reminders.get(key)
        color = REMINDER_COLORS.get(reminder["color"]) if reminder else VALUE_COLORS.get(value)
        if color:
            return color, "white", self.image_font_special if value not in self.shifts else self.image_font_shift
        if value:
            return ("#3B8ED0", "#159DB5"), "white", self.image_font_shift
        return ("#F9F9FA", "#159DB5"), ("#111111", "white"), self.image_font_normal

    def _redraw(self):
        if self._drawing_suspended or not hasattr(self, "canvas"):
            return
        self.canvas.delete("table")
        surface = self._theme_color(TABLE_SURFACE)
        self.canvas.configure(bg=surface)
        height = self.rows[-1]["y1"] + 4
        image = Image.new("RGB", (self.table_width, height), surface)
        self._draw = ImageDraw.Draw(image)
        for row in self.rows:
            y0, y1, kind = row["y0"], row["y1"], row["kind"]
            if kind == "header":
                self._cell(0, y0, self.name_width, y1, TABLE_SURFACE, "Empleado", font=self.image_font_heading, anchor="w")
                for day, title in enumerate(DAYS):
                    x0, x1 = self._day_x(day), self._day_x(day + 1)
                    self._cell(x0, y0, x1, y1, TABLE_SURFACE, title, font=self.image_font_heading)
            elif kind == "section":
                self._cell(0, y0, self.table_width, y1, ("#F4E84A", "#756D10"), row["title"], ("#111111", "white"), self.image_font_bold, "w")
                if row["title"] == "Trabajadores en servicio":
                    self._draw_coverage_legend(y0, y1)
            elif kind == "employee":
                employee, name_end = row["employee"], self.name_width
                if employee["categoria"] == "ETT":
                    name_end -= 82
                self._cell(0, y0, name_end, y1, TABLE_SURFACE, employee["nombre"], font=self.image_font_name, anchor="w")
                if employee["categoria"] == "ETT":
                    employee_id = employee["id"]
                    self._cell(name_end, y0, self.name_width, y1, self.ett_hour_colors.get(employee_id, ("#E67E22", "#CA6F1E")), self.ett_hour_vars[employee_id].get(), "white", self.image_font_small)
                    self._dropdown_arrow(self.name_width - 11, (y0 + y1) / 2, "white")
                for day in range(7):
                    key, x0, x1 = (employee["id"], day), self._day_x(day), self._day_x(day + 1)
                    value = self.assignment_vars[key].get()
                    background, foreground, font = self._assignment_style(key, value)
                    self._cell(x0, y0, x1 - 28, y1, background, value, foreground, font)
                    self._dropdown_arrow(x1 - 39, (y0 + y1) / 2, foreground)
                    reminder = self.reminders.get(key)
                    reminder_color = REMINDER_COLORS.get(reminder["color"]) if reminder else ("#AEB5BA", "#4E555A")
                    self._cell(x1 - 28, y0, x1, y1, reminder_color, "!" if reminder else "●", "white", self.image_font_bold)
            elif kind == "client":
                service = row["service"]
                self._cell(0, y0, self.name_width, y1, TABLE_SURFACE, service.replace("_", " ").title(), font=self.image_font_bold, anchor="w")
                for day in range(7):
                    x0, x1 = self._day_x(day), self._day_x(day + 1)
                    self._cell(x0, y0, x1, y1, ("#F9F9FA", "#343638"), self.client_vars[(service, day)].get(), font=self.image_font_bold)
            elif kind == "coverage":
                service = row["service"]
                self._cell(0, y0, self.name_width, y1, TABLE_SURFACE, service.title(), font=self.image_font_normal, anchor="w")
                for day in range(7):
                    x0, x1, display = self._day_x(day), self._day_x(day + 1), self.coverage_labels[(service, day)]
                    self._cell(x0, y0, x1, y1, display.cget("fg_color"), display.cget("text"), font=self.image_font_bold)
            elif kind in ("opening", "guard"):
                opening = kind == "opening"
                label = "Apertura" if opening else "Guardia"
                heading_color = ("#B8E33D", "#466819") if opening else ("#B9D7EA", "#1F4E68")
                self._cell(0, y0, self.name_width, y1, heading_color, label, font=self.image_font_bold, anchor="w")
                values = self.opening_labels if opening else self.guard_labels
                for day in range(7):
                    x0, x1, display = self._day_x(day), self._day_x(day + 1), values[day]
                    self._cell(x0, y0, x1, y1, display.cget("fg_color"), display.cget("text"), display.cget("text_color"), self.image_font_small)
            elif kind == "reminders":
                self._cell(0, y0, self.table_width, y1, ("#FFF3CD", "#55450D"), self.reminder_summary.cget("text"), font=self.image_font_small, anchor="w")
        self._draw = None
        self._table_image = ImageTk.PhotoImage(image)
        self.canvas.create_image(0, 0, image=self._table_image, anchor="nw", tags="table")
        self._schedule_scrollbar_update()

    def _draw_coverage_legend(self, y0, y1):
        entries = coverage_legend(self._coverage_mode)
        text_color = self._theme_color(("#111111", "white"))
        box_size, gap, item_gap = 12, 5, 16
        widths = []
        for _color, label in entries:
            bounds = self._draw.textbbox((0, 0), label, font=self.image_font_small)
            widths.append(box_size + gap + bounds[2] - bounds[0])
        x = self.table_width - 10 - sum(widths) - item_gap * (len(entries) - 1)
        # On very narrow/scaled layouts, keep the title readable and shorten the longest explanation.
        if x < self.name_width:
            entries = (("red", "Falta"), ("yellow", "Servicio posible"), ("green", "OK"), ("purple", "Sobra")) if self._coverage_mode != "automatic" else (("red", "Faltan"), ("green", "OK"), ("purple", "Exceso"))
            widths = []
            for _color, label in entries:
                bounds = self._draw.textbbox((0, 0), label, font=self.image_font_small)
                widths.append(box_size + gap + bounds[2] - bounds[0])
            x = max(self.name_width, self.table_width - 10 - sum(widths) - item_gap * (len(entries) - 1))
        center_y = (y0 + y1) / 2
        for (color, label), width in zip(entries, widths):
            fill = self._theme_color(COVERAGE_COLORS[color])
            self._draw.rounded_rectangle(
                (x, center_y - box_size / 2, x + box_size, center_y + box_size / 2), radius=3, fill=fill,
            )
            self._draw.text((x + box_size + gap, center_y), label, fill=text_color, font=self.image_font_small, anchor="lm")
            x += width + item_gap

    def open_saved_weeks(self):
        window = ctk.CTkToplevel(self.parent)
        window.title("Semanas guardadas")
        window.transient(self.app)
        window.minsize(520, 360)
        remember_window(window, "saved_weeks", "620x460")
        ctk.CTkLabel(window, text="Semanas almacenadas", font=ctk.CTkFont(size=18, weight="bold")).pack(
            anchor="w", padx=20, pady=(18, 8)
        )
        ctk.CTkLabel(window, text="Haz doble clic sobre una semana para cargarla.", text_color="gray").pack(
            anchor="w", padx=20, pady=(0, 10)
        )
        frame = ctk.CTkFrame(window)
        frame.pack(fill="both", expand=True, padx=20, pady=(0, 12))
        style = ttk.Style(window)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style_name = "SavedWeeks.Treeview"
        dark = ctk.get_appearance_mode().lower() == "dark"
        style.configure(
            style_name, background="#343638" if dark else "#F5F5F5",
            fieldbackground="#343638" if dark else "#F5F5F5", foreground="#F3F3F3" if dark else "#111111",
            rowheight=32, borderwidth=0,
        )
        style.configure(
            f"{style_name}.Heading", background="#60666A" if dark else "#D0D0D0",
            foreground="#FFFFFF" if dark else "#111111", relief="flat", borderwidth=1,
        )
        style.map(f"{style_name}.Heading", background=[("active", "#3B8ED0")], foreground=[("active", "white")])
        style.map(style_name, background=[("selected", "#1F6AA5")], foreground=[("selected", "white")])
        tree = ttk.Treeview(
            frame, columns=("inicio", "fin"), show="headings", selectmode="browse", style=style_name,
        )
        tree.column("inicio", width=220, anchor="center")
        tree.column("fin", width=220, anchor="center")
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        scrollbar.pack(side="right", fill="y", padx=(0, 8), pady=8)

        with connect() as conn:
            stored_dates = [row[0] for row in conn.execute(
                "SELECT fecha FROM clientes UNION SELECT fecha FROM asignaciones ORDER BY fecha DESC"
            )]
        mondays = sorted({parse_week(value) for value in stored_dates}, reverse=True)
        sort_state = {"column": "inicio", "descending": True}

        def sort_weeks(column):
            if sort_state["column"] == column:
                sort_state["descending"] = not sort_state["descending"]
            else:
                sort_state.update(column=column, descending=False)
            for item in tree.get_children():
                tree.delete(item)
            ordered = sorted(mondays, reverse=sort_state["descending"])
            arrow = " ↓" if sort_state["descending"] else " ↑"
            tree.heading("inicio", text="Semana del" + (arrow if column == "inicio" else ""), command=lambda: sort_weeks("inicio"))
            tree.heading("fin", text="Hasta" + (arrow if column == "fin" else ""), command=lambda: sort_weeks("fin"))
            for monday in ordered:
                tree.insert("", "end", iid=monday.isoformat(), values=(f"{monday:%d/%m/%Y}", f"{monday + timedelta(days=6):%d/%m/%Y}"))

        # Primera carga: semanas más recientes arriba.
        sort_state["descending"] = False
        sort_weeks("inicio")

        if not mondays:
            ctk.CTkLabel(frame, text="Todavía no hay semanas guardadas.", text_color="gray").place(relx=0.5, rely=0.5, anchor="center")

        def load_selected(_event=None):
            selected = tree.selection()
            if not selected:
                return
            monday = date.fromisoformat(selected[0])
            self.week_var.set(monday.strftime("%d/%m/%Y"))
            window.destroy()
            self.load_week()

        tree.bind("<Double-1>", load_selected)
        tree.bind("<Return>", load_selected)
        ctk.CTkButton(window, text="Cargar semana", command=load_selected).pack(pady=(0, 16))
        return window

    def apply_appearance(self):
        self.toolbar.configure(bg=self._theme_color(TABLE_SURFACE))
        self.canvas_frame.configure(bg=self._theme_color(TABLE_SURFACE))
        self._build_assignment_menu()
        self._build_ett_menu()
        self._redraw()

    def apply_display_settings(self):
        """Apply font-size and theme preferences without rebuilding the table."""
        self._create_shared_fonts()
        self.apply_appearance()

    def refresh_catalogues(self):
        preserved = {key: variable.get() for key, variable in self.assignment_vars.items()}
        clients = {key: variable.get() for key, variable in self.client_vars.items()}
        targets = dict(self.ett_targets)
        self._render_grid()
        self.ett_targets.update({key: value for key, value in targets.items() if key in self.ett_hour_vars})
        self.reminders = {key: value for key, value in self.reminders.items() if key in self.assignment_vars}
        for key, value in preserved.items():
            if key in self.assignment_vars and value in self.options:
                self.assignment_vars[key].set(value)
        for key, value in clients.items():
            if key in self.client_vars:
                self.client_vars[key].set(value)
        self.recalculate()

    def _assignment_changed(self, employee_id, day_index, value):
        if value not in self.shifts:
            self.reminders.pop((employee_id, day_index), None)
        self.recalculate()

    def _ett_target_changed(self, employee_id, value):
        try:
            self.ett_targets[employee_id] = int(str(value).split()[0])
        except (ValueError, IndexError):
            return
        self.recalculate()

    @staticmethod
    def _hours_text(value):
        return str(int(value)) if float(value).is_integer() else f"{value:.1f}".replace(".", ",")

    def _refresh_ett_hours(self):
        for employee_id, variable in self.ett_hour_vars.items():
            assigned = sum(float(self.shifts[value]["horas"]) for day in range(7) if (value := self.assignment_vars[(employee_id, day)].get()) in self.shifts)
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
            self.ett_hour_colors[employee_id] = color

    def _paint_assignment(self, _key, _value):
        self._redraw()

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
        ctk.CTkLabel(dialog, text=f'{employee["nombre"]} · {DAYS[day_index]} · {value}', font=ctk.CTkFont(size=17, weight="bold")).pack(pady=(20, 12))
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
            self.recalculate()
            dialog.destroy()

        def clear_reminder():
            self.reminders.pop((employee_id, day_index), None)
            self.recalculate()
            dialog.destroy()

        ctk.CTkButton(actions, text="Quitar aviso", fg_color="#8B3A3A", command=clear_reminder).pack(side="left")
        ctk.CTkButton(actions, text="Guardar aviso", command=save_reminder).pack(side="right")
        dialog.after_idle(lambda: apply_native_titlebar(dialog, redraw=True))
        return dialog

    def _dates(self):
        monday = parse_week(self.week_var.get())
        return monday, [(monday + timedelta(days=index)).isoformat() for index in range(7)]

    def load_week(self):
        try:
            monday, dates = self._dates()
            self.week_var.set(monday.strftime("%d/%m/%Y"))
            self.week_title.configure(text=f"Semana del {monday:%d/%m/%Y} al {(monday + timedelta(days=6)):%d/%m/%Y}")
            with connect() as conn:
                assignment_rows = conn.execute("SELECT empleado_id,fecha,valor,color,nota FROM asignaciones WHERE fecha BETWEEN ? AND ?", (dates[0], dates[-1])).fetchall()
                assignments = {(row["empleado_id"], row["fecha"]): row["valor"] for row in assignment_rows}
                saved_reminders = {(row["empleado_id"], row["fecha"]): {"color": row["color"], "nota": row["nota"]} for row in assignment_rows if row["color"]}
                clients = {row["fecha"]: row for row in conn.execute("SELECT * FROM clientes WHERE fecha BETWEEN ? AND ?", (dates[0], dates[-1]))}
                ett_targets = {row["empleado_id"]: row["horas_objetivo"] for row in conn.execute("SELECT empleado_id,horas_objetivo FROM ett_horas_semana WHERE semana=?", (dates[0],))}
            self._drawing_suspended = True
            self.ett_targets = {employee_id: int(ett_targets.get(employee_id, 40)) for employee_id in self.ett_hour_vars}
            self.reminders.clear()
            for (employee_id, day_index), variable in self.assignment_vars.items():
                value = assignments.get((employee_id, dates[day_index]), "")
                variable.set(value if value in self.options else "")
                reminder = saved_reminders.get((employee_id, dates[day_index]))
                if reminder:
                    self.reminders[(employee_id, day_index)] = reminder
            for (service, day_index), variable in self.client_vars.items():
                row = clients.get(dates[day_index])
                variable.set(str(row[service] if row else 0))
            self._drawing_suspended = False
            self.recalculate()
        except Exception as exc:
            self._drawing_suspended = False
            messagebox.showerror("No se pudo cargar", str(exc), parent=self.parent)

    def recalculate(self):
        settings = load_settings()
        automatic = settings.get("coverage_mode") == "automatic"
        self._coverage_mode = "automatic" if automatic else "manual"
        employee_names = {row["id"]: row["nombre"] for row in self.employees}
        for day_index in range(7):
            counts = {service: 0 for service in ("desayuno", "almuerzo", "cena")}
            openings, guards = [], []
            for employee in self.employees:
                shift = self.shifts.get(self.assignment_vars[(employee["id"], day_index)].get())
                if not shift:
                    continue
                if not automatic or category_counts_for_automatic_coverage(employee["categoria"], settings):
                    for service in counts:
                        counts[service] += int(bool(shift[service]))
                if shift["apertura"]:
                    openings.append(employee_names[employee["id"]])
                if shift.get("guardia"):
                    guards.append(employee_names[employee["id"]])
            for service, count in counts.items():
                if automatic:
                    try:
                        clients = int(self.client_vars[(service, day_index)].get().strip() or "0")
                    except ValueError:
                        clients = 0
                    required = automatic_workers_required(clients)
                    color = "red" if count < required else "green" if count == required else "purple"
                    text = f"{count} / {required}"
                else:
                    limits = settings["coverage"][service]
                    color = "purple" if count >= int(limits["purple"]) else "green" if count >= int(limits["green"]) else "yellow" if count >= int(limits["yellow"]) else "red"
                    text = str(count)
                self.coverage_labels[(service, day_index)].configure(text=text, fg_color=COVERAGE_COLORS[color])
            opening_label = self.opening_labels[day_index]
            if len(openings) > 1:
                opening_label.configure(text="DUPLICADO: " + " / ".join(openings), fg_color=VALUE_COLORS["FALTA"], text_color="white")
            elif openings:
                opening_label.configure(text=openings[0], fg_color=("#D9F09B", "#345019"), text_color=("#111111", "white"))
            else:
                opening_label.configure(text="SIN APERTURA", fg_color=("#FFD2B3", "#713B18"), text_color=("#111111", "white"))
            guard_label = self.guard_labels[day_index]
            if len(guards) > 1:
                guard_label.configure(text="DUPLICADO: " + " / ".join(guards), fg_color=VALUE_COLORS["FALTA"], text_color="white")
            elif guards:
                guard_label.configure(text=guards[0], fg_color=("#D7EBF7", "#245B78"), text_color=("#111111", "white"))
            else:
                guard_label.configure(text="SIN GUARDIA", fg_color=("#FFD2B3", "#713B18"), text_color=("#111111", "white"))
        self._refresh_ett_hours()
        reminder_lines = [f'{DAYS[day]} · {employee_names[employee]}: {reminder["nota"] or "Sin detalle"}' for (employee, day), reminder in sorted(self.reminders.items(), key=lambda item: (item[0][1], item[0][0]))]
        self.reminder_summary.configure(text="Recordatorios: " + "   |   ".join(reminder_lines) if reminder_lines else "Sin recordatorios especiales esta semana.")
        self._redraw()

    def save(self):
        self._close_editor(commit=True)
        try:
            _monday, dates = self._dates()
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
                    number = int(self.client_vars[(service, day_index)].get().strip() or "0")
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
                conn.executemany("INSERT INTO ett_horas_semana(semana,empleado_id,horas_objetivo) VALUES (?,?,?)", [(dates[0], employee_id, self.ett_targets.get(employee_id, 40)) for employee_id in self.ett_hour_vars])
            self.recalculate()
            duplicates = [DAYS[index] for index, label in self.opening_labels.items() if str(label.cget("text")).startswith("DUPLICADO")]
            warning = f"\n\nRevisa aperturas duplicadas: {', '.join(duplicates)}." if duplicates else ""
            messagebox.showinfo("Cuadrante", f"Semana guardada correctamente.{warning}", parent=self.parent)
        except (ValueError, TypeError) as exc:
            messagebox.showerror("Datos incorrectos", str(exc), parent=self.parent)
        except Exception as exc:
            messagebox.showerror("No se pudo guardar", str(exc), parent=self.parent)

    def export_pdf(self):
        self._close_editor(commit=True)
        try:
            from reports import export_schedule_pdf
            monday, _dates = self._dates()
            path = export_schedule_pdf(self, monday)
            messagebox.showinfo("Informe creado", f"Se ha creado:\n\n{path}", parent=self.parent)
        except Exception as exc:
            messagebox.showerror("No se pudo exportar", str(exc), parent=self.parent)
