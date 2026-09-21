import customtkinter as ctk
from PIL import Image
from tkinter import filedialog, messagebox

from core.backup import backup_on_start_if_enabled
from core.database import initialize_database
from core.paths import APP_DIR
from core.settings import backup_directory, configured_path, detected_onedrive, load_settings, save_settings
from modules.catalogos import employee_manager, shift_manager
from modules.cuadrante import build_cuadrante


initial = load_settings()
ctk.set_appearance_mode(initial.get("appearance_mode", "Dark"))
ctk.set_default_color_theme("blue")
ctk.set_widget_scaling(float(initial.get("font_scale", 1.0)))


class CuadranteApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        initialize_database()
        self.geometry("1380x880")
        self.minsize(1120, 720)
        self.last_backup = None
        self.backup_error = None
        try:
            self.last_backup = backup_on_start_if_enabled()
        except Exception as exc:
            self.backup_error = str(exc)
        self._build_header()
        self.tabs = ctk.CTkTabview(self, corner_radius=10)
        self.tabs.pack(fill="both", expand=True, padx=15, pady=10)
        tab = self.tabs.add("Cuadrante semanal")
        build_cuadrante(tab, self)
        self.schedule = tab._controller
        if self.backup_error:
            self.after(250, lambda: messagebox.showwarning("Copia de seguridad", self.backup_error, parent=self))

    def _build_header(self):
        header = ctk.CTkFrame(self, corner_radius=10)
        header.pack(fill="x", padx=15, pady=(15, 5))
        self.logo_label = ctk.CTkLabel(header, text="", width=1)
        titles = ctk.CTkFrame(header, fg_color="transparent")
        titles.pack(side="left", padx=15, pady=14)
        self.title_label = ctk.CTkLabel(titles, text="", font=ctk.CTkFont(size=22, weight="bold"))
        self.title_label.pack(anchor="w")
        ctk.CTkLabel(titles, text="Planificación semanal de turnos y cobertura de servicios", text_color="gray").pack(anchor="w")
        self.theme_switch = ctk.CTkSwitch(header, text="Modo oscuro", command=self._toggle_theme)
        if str(load_settings().get("appearance_mode", "Dark")).lower() == "dark":
            self.theme_switch.select()
        self.theme_switch.pack(side="right", padx=(8, 18))
        ctk.CTkButton(header, text="⚙", width=42, height=36, font=ctk.CTkFont(size=20), command=self.open_settings).pack(side="right", padx=5)
        self._refresh_branding()

    def _toggle_theme(self):
        mode = "Dark" if self.theme_switch.get() else "Light"
        ctk.set_appearance_mode(mode)
        values = load_settings()
        values["appearance_mode"] = mode
        save_settings(values)

    def _refresh_branding(self):
        settings = load_settings()
        name = str(settings.get("app_name") or "Cuadrante")
        self.title(f"{name} - Cuadrantes")
        self.title_label.configure(text=name)
        value = str(settings.get("logo_path") or "").strip()
        if value:
            path = configured_path("logo_path")
            if path.is_file():
                try:
                    image = Image.open(path)
                    image.thumbnail((64, 64), Image.Resampling.LANCZOS)
                    self._logo_image = ctk.CTkImage(light_image=image, dark_image=image, size=image.size)
                    self.logo_label.configure(image=self._logo_image)
                    if not self.logo_label.winfo_manager():
                        self.logo_label.pack(side="left", padx=(15, 0), pady=8, before=self.title_label.master)
                    return
                except OSError:
                    pass
        self.logo_label.configure(image=None)
        self.logo_label.pack_forget()

    def open_employee_manager(self):
        employee_manager(self, self.schedule.refresh_catalogues)

    def open_shift_manager(self):
        shift_manager(self, self.schedule.refresh_catalogues)

    def open_settings(self):
        window = ctk.CTkToplevel(self)
        window.title("Ajustes")
        window.geometry("780x760")
        window.transient(self)
        window.grab_set()
        body = ctk.CTkScrollableFrame(window, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=(18, 4))
        current = load_settings()

        def heading(text):
            ctk.CTkLabel(body, text=text, font=ctk.CTkFont(size=15, weight="bold")).pack(anchor="w", pady=(12, 5))

        heading("Identidad y visualización")
        name = ctk.StringVar(value=str(current.get("app_name", "Cuadrante")))
        ctk.CTkEntry(body, textvariable=name, placeholder_text="Nombre de la aplicación").pack(fill="x", pady=(0, 8))
        logo = ctk.StringVar(value=str(current.get("logo_path", "")))
        logo_row = ctk.CTkFrame(body, fg_color="transparent")
        logo_row.pack(fill="x", pady=(0, 8))
        ctk.CTkEntry(logo_row, textvariable=logo, placeholder_text="Logo opcional").pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(logo_row, text="Elegir…", width=85, command=lambda: self._choose_file(window, logo)).pack(side="left", padx=3)
        ctk.CTkButton(logo_row, text="Quitar", width=70, fg_color="#8B3A3A", command=lambda: logo.set("")).pack(side="left", padx=3)
        font = ctk.StringVar(value=f'{round(float(current.get("font_scale", 1.0)) * 100)} %')
        font_row = ctk.CTkFrame(body, fg_color="transparent")
        font_row.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(font_row, text="Tamaño de fuente").pack(side="left")
        ctk.CTkOptionMenu(font_row, variable=font, values=[f"{value} %" for value in range(80, 151, 10)], width=110).pack(side="right")

        heading("Archivos y copias de seguridad")
        reports = ctk.StringVar(value=str(configured_path("reports_directory")))
        database = ctk.StringVar(value=str(configured_path("database_path")))
        backup = ctk.StringVar(value=str(backup_directory() or ""))
        backup_enabled = ctk.BooleanVar(value=bool(current.get("backup_on_start", False)))
        self._path_row(body, "Carpeta de informes", reports, window, folder=True)
        self._path_row(body, "Base de datos", database, window, folder=False, database=True)
        ctk.CTkSwitch(body, text="Copia automática al iniciar", variable=backup_enabled).pack(anchor="w", pady=(8, 4))
        self._path_row(body, "Carpeta de OneDrive", backup, window, folder=True)

        def detect():
            root = detected_onedrive()
            if root:
                backup.set(str(root / "Cuadrante" / "Backups"))
            else:
                messagebox.showwarning("OneDrive", "No se ha detectado una carpeta local de OneDrive.", parent=window)

        ctk.CTkButton(body, text="Detectar OneDrive", width=150, command=detect).pack(anchor="e", pady=(0, 8))

        heading("Cobertura mínima por servicio")
        ctk.CTkLabel(body, text="Amarillo avisa de cobertura justa; verde es la dotación prevista; morado indica personal por encima de la previsión.", text_color="gray", wraplength=700, justify="left").pack(anchor="w", pady=(0, 8))
        coverage_vars = {}
        for service in ("desayuno", "almuerzo", "cena"):
            row = ctk.CTkFrame(body)
            row.pack(fill="x", pady=3)
            ctk.CTkLabel(row, text=service.title(), width=115, anchor="w").pack(side="left", padx=10, pady=8)
            for label, key in (("Amarillo", "yellow"), ("Verde", "green"), ("Morado", "purple")):
                ctk.CTkLabel(row, text=label).pack(side="left", padx=(8, 3))
                variable = ctk.StringVar(value=str(current["coverage"][service][key]))
                coverage_vars[(service, key)] = variable
                ctk.CTkEntry(row, textvariable=variable, width=45, justify="center").pack(side="left")

        def save():
            try:
                scale = int(font.get().split()[0]) / 100
                coverage = {}
                for service in ("desayuno", "almuerzo", "cena"):
                    values = {key: int(coverage_vars[(service, key)].get()) for key in ("yellow", "green", "purple")}
                    if not (0 <= values["yellow"] < values["green"] < values["purple"]):
                        raise ValueError(f"Los niveles de {service} deben aumentar de amarillo a morado.")
                    coverage[service] = values
                if not name.get().strip():
                    raise ValueError("El nombre de la aplicación no puede estar vacío.")
                values = {
                    **load_settings(), "app_name": name.get().strip(), "logo_path": logo.get().strip(),
                    "font_scale": scale, "reports_directory": reports.get().strip(),
                    "database_path": database.get().strip(), "backup_on_start": backup_enabled.get(),
                    "backup_directory": backup.get().strip(), "coverage": coverage,
                }
                save_settings(values)
                configured_path("reports_directory").mkdir(parents=True, exist_ok=True)
                if backup_enabled.get() and backup.get().strip():
                    backup_directory().mkdir(parents=True, exist_ok=True)
                ctk.set_widget_scaling(scale)
                self._refresh_branding()
                self.schedule.recalculate()
                window.destroy()
                messagebox.showinfo("Ajustes", "Los ajustes se han guardado. Si cambiaste la base de datos, reinicia la aplicación.", parent=self)
            except (ValueError, OSError) as exc:
                messagebox.showerror("Ajustes", str(exc), parent=window)

        ctk.CTkButton(window, text="Guardar ajustes", command=save).pack(fill="x", padx=24, pady=16)

    @staticmethod
    def _choose_file(parent, variable):
        selected = filedialog.askopenfilename(parent=parent, filetypes=(("Imágenes", "*.png *.jpg *.jpeg *.webp"), ("Todos", "*.*")))
        if selected:
            variable.set(selected)

    @staticmethod
    def _path_row(parent, label, variable, window, folder=True, database=False):
        ctk.CTkLabel(parent, text=label).pack(anchor="w", pady=(5, 2))
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x")
        ctk.CTkEntry(row, textvariable=variable).pack(side="left", fill="x", expand=True, padx=(0, 8))

        def choose():
            if folder:
                selected = filedialog.askdirectory(parent=window, initialdir=variable.get() or str(APP_DIR))
            else:
                selected = filedialog.asksaveasfilename(parent=window, initialfile="cuadrante.db", defaultextension=".db", filetypes=(("Base de datos", "*.db"),))
            if selected:
                variable.set(selected)

        ctk.CTkButton(row, text="Examinar…", width=95, command=choose).pack(side="right")


if __name__ == "__main__":
    CuadranteApp().mainloop()

