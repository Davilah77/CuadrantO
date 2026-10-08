import customtkinter as ctk
from PIL import Image, ImageTk
import sys
import threading
import webbrowser
import tkinter as tk
from tkinter import filedialog, messagebox

from core.backup import backup_on_start_if_enabled
from core.database import initialize_database
from core.paths import APP_DIR, resource_path
from core.settings import app_logo_path, backup_directory, configured_path, detected_onedrive, load_settings, save_settings
from core.updater import RELEASES_URL, UpdateError, check_for_update, download_and_stage, launch_installer
from core.version import __version__
from core.window_state import apply_native_titlebar, remember_window
from modules.catalogos import employee_manager, shift_manager
from modules.cuadrante import build_cuadrante


initial = load_settings()

if sys.platform == "win32":
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Davilah.CuadrantO")
    except Exception:
        pass

ctk.set_appearance_mode(initial.get("appearance_mode", "Dark"))
ctk.set_default_color_theme("blue")
ctk.set_widget_scaling(float(initial.get("font_scale", 1.0)))


class CuadranteApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        # Build the dense schedule off-screen so startup never paints row by row.
        self.withdraw()
        initialize_database()
        self.minsize(1120, 720)
        remember_window(self, "main", "1380x880")
        self.last_backup = None
        self.backup_error = None
        try:
            self.last_backup = backup_on_start_if_enabled()
        except Exception as exc:
            self.backup_error = str(exc)
        self._build_header()
        self._build_update_banner()
        # There is only one workspace. A full CTkTabview was needlessly
        # redrawing several canvases on every resize, so we keep its visual
        # tab label with a much lighter container.
        self.content = tk.Frame(self, bg=self._surface_color(), bd=0, highlightthickness=0)
        self.content.pack(fill="both", expand=True, padx=15, pady=10)
        ctk.CTkLabel(
            self.content, text="Cuadrante semanal", fg_color=("#3B8ED0", "#1F6AA5"),
            text_color="white", corner_radius=8, height=28,
        ).pack(pady=(0, 3))
        tab = tk.Frame(self.content, bg=self._surface_color(), bd=0, highlightthickness=0)
        tab.pack(fill="both", expand=True)
        self.tab_body = tab
        build_cuadrante(tab, self)
        self.schedule = tab._controller
        self.after_idle(self._show_ready)
        if self.backup_error:
            self.after(250, lambda: messagebox.showwarning("Copia de seguridad", self.backup_error, parent=self))
        if load_settings().get("check_updates_on_start", True):
            self.after(1200, lambda: self.check_updates(silent=True))

    def _show_ready(self):
        self.deiconify()
        self.lift()

    def _build_header(self):
        header = ctk.CTkFrame(self, corner_radius=10)
        header.pack(fill="x", padx=15, pady=(8, 4))
        self.product_icon_label = ctk.CTkLabel(header, text="", width=1)
        self.product_icon_label.pack(side="left", padx=(10, 0), pady=4)
        self.logo_label = ctk.CTkLabel(header, text="", width=1)
        titles = ctk.CTkFrame(header, fg_color="transparent")
        titles.pack(side="left", padx=10, pady=4)
        self.title_label = ctk.CTkLabel(titles, text="", font=ctk.CTkFont(size=18, weight="bold"), height=22)
        self.title_label.pack(anchor="w")
        self.subtitle_label = ctk.CTkLabel(
            titles, text="", text_color="gray", font=ctk.CTkFont(size=11, weight="bold"), height=16,
        )
        self.subtitle_label.pack(anchor="w")
        self.theme_switch = ctk.CTkSwitch(header, text="Modo oscuro", command=self._toggle_theme)
        if str(load_settings().get("appearance_mode", "Dark")).lower() == "dark":
            self.theme_switch.select()
        self.theme_switch.pack(side="right", padx=(8, 18))
        ctk.CTkButton(header, text="⚙", width=42, height=36, font=ctk.CTkFont(size=20), command=self.open_settings).pack(side="right", padx=5)
        self.update_button = ctk.CTkButton(header, text="↻", width=42, height=36, font=ctk.CTkFont(size=20), command=self.check_updates)
        self.update_button.pack(side="right", padx=5)
        ctk.CTkButton(header, text="ⓘ", width=42, height=36, font=ctk.CTkFont(size=18), command=self.open_about).pack(side="right", padx=5)
        self._refresh_branding()

    def _build_update_banner(self):
        self.available_update = None
        self.update_banner = ctk.CTkFrame(self, fg_color=("#D7EBF7", "#173E55"), corner_radius=8)
        self.update_banner_label = ctk.CTkLabel(self.update_banner, text="", anchor="w", font=ctk.CTkFont(weight="bold"))
        self.update_banner_label.pack(side="left", fill="x", expand=True, padx=14, pady=9)
        ctk.CTkButton(self.update_banner, text="Ahora no", width=82, fg_color="gray45", command=self.update_banner.pack_forget).pack(side="right", padx=(4, 10), pady=7)
        ctk.CTkButton(self.update_banner, text="Actualizar", width=92, command=self.install_available_update).pack(side="right", padx=4, pady=7)
        ctk.CTkButton(self.update_banner, text="Novedades", width=90, command=self.show_release_notes).pack(side="right", padx=4, pady=7)

    def _toggle_theme(self):
        mode = "Dark" if self.theme_switch.get() else "Light"
        ctk.set_appearance_mode(mode)
        self.content.configure(bg=self._surface_color())
        self.tab_body.configure(bg=self._surface_color())
        if hasattr(self, "schedule"):
            self.schedule.apply_appearance()
        values = load_settings()
        values["appearance_mode"] = mode
        save_settings(values)

    @staticmethod
    def _surface_color():
        return "#2B2B2B" if ctk.get_appearance_mode().lower() == "dark" else "#DBDBDB"

    def _refresh_branding(self):
        settings = load_settings()
        name = str(settings.get("app_name") or "CuadrantO")
        self.title(f"{name} · CuadrantO {__version__}")
        self.title_label.configure(text=f"CuadrantO · versión {__version__}")
        subtitle = "Planificación semanal de turnos y cobertura de servicios"
        self.subtitle_label.configure(text=f"{name} · {subtitle}" if name.lower() != "cuadranto" else subtitle)
        product_icon = resource_path("assets/CuadrantO.png")
        if product_icon.is_file():
            try:
                icon_image = Image.open(product_icon).convert("RGBA")
                if icon_image.getbbox():
                    icon_image = icon_image.crop(icon_image.getbbox())
                window_icon = icon_image.copy()
                window_icon.thumbnail((256, 256), Image.Resampling.LANCZOS)
                self._window_icon = ImageTk.PhotoImage(window_icon)
                self.iconphoto(True, self._window_icon)
                header_icon = icon_image.copy()
                header_icon.thumbnail((40, 40), Image.Resampling.LANCZOS)
                self._product_icon_image = ctk.CTkImage(light_image=header_icon, dark_image=header_icon, size=header_icon.size)
                self.product_icon_label.configure(image=self._product_icon_image)
            except OSError:
                pass
        if sys.platform == "win32":
            ico_path = resource_path("assets/CuadrantO.ico")
            if ico_path.is_file():
                try:
                    self.iconbitmap(str(ico_path))
                except Exception:
                    pass
        path = app_logo_path()
        if path and path.is_file():
            try:
                image = Image.open(path).convert("RGBA")
                image.thumbnail((40, 40), Image.Resampling.LANCZOS)
                self._logo_image = ctk.CTkImage(light_image=image, dark_image=image, size=image.size)
                self.logo_label.configure(image=self._logo_image)
                if not self.logo_label.winfo_manager():
                    self.logo_label.pack(side="left", padx=(10, 0), pady=4, before=self.title_label.master)
                return
            except OSError:
                pass
        self.logo_label.configure(image=None)
        self.logo_label.pack_forget()

    def check_updates(self, silent=False):
        self.update_button.configure(state="disabled", text="…")
        include_beta = bool(load_settings().get("include_prereleases", True))

        def work():
            try:
                result = check_for_update(include_beta)
                self.after(0, lambda: self._update_check_finished(result, silent, None))
            except Exception as exc:
                self.after(0, lambda error=exc: self._update_check_finished(None, silent, error))

        threading.Thread(target=work, daemon=True).start()

    def _update_check_finished(self, result, silent, error):
        self.update_button.configure(state="normal", text="↻")
        if error:
            if not silent:
                messagebox.showwarning("Actualizaciones", str(error), parent=self)
            return
        if result is None:
            if not silent:
                messagebox.showinfo("Actualizaciones", f"CuadrantO {__version__} es la versión más reciente.", parent=self)
            return
        self.available_update = result
        self.update_banner_label.configure(text=f"Nueva versión disponible: CuadrantO {result.version}")
        if not self.update_banner.winfo_manager():
            self.update_banner.pack(fill="x", padx=15, pady=(5, 0), before=self.content)

    def show_release_notes(self):
        if not self.available_update:
            return
        notes = self.available_update.notes.strip() or "Esta versión no incluye notas adicionales."
        window = ctk.CTkToplevel(self)
        window.title(f"Novedades · {self.available_update.version}")
        remember_window(window, "release_notes", "650x500")
        window.transient(self)
        ctk.CTkLabel(window, text=self.available_update.title, font=ctk.CTkFont(size=19, weight="bold")).pack(pady=(20, 10))
        text = ctk.CTkTextbox(window, wrap="word")
        text.pack(fill="both", expand=True, padx=20, pady=(0, 12))
        text.insert("1.0", notes)
        text.configure(state="disabled")
        ctk.CTkButton(window, text="Abrir en GitHub", command=lambda: webbrowser.open(self.available_update.page_url)).pack(pady=(0, 18))

    def install_available_update(self):
        info = self.available_update
        if not info:
            return
        if not messagebox.askyesno(
            "Instalar actualización",
            f"Se descargará CuadrantO {info.version}.\n\nAntes de actualizar se creará una copia de seguridad y la aplicación se reiniciará. ¿Continuar?",
            parent=self,
        ):
            return
        self.update_banner_label.configure(text=f"Descargando CuadrantO {info.version}…")

        def work():
            try:
                staged = download_and_stage(info)
                launch_installer(staged)
                self.after(0, self.destroy)
            except Exception as exc:
                self.after(0, lambda error=exc: self._update_install_failed(error))

        threading.Thread(target=work, daemon=True).start()

    def _update_install_failed(self, error):
        self.update_banner_label.configure(text=f"Nueva versión disponible: CuadrantO {self.available_update.version}")
        messagebox.showerror("No se pudo actualizar", str(error), parent=self)

    def open_about(self):
        window = ctk.CTkToplevel(self)
        window.title("Acerca de CuadrantO")
        remember_window(window, "about", "620x560")
        window.transient(self)
        logo_path = resource_path("assets/CuadrantO.png")
        if logo_path.is_file():
            image = Image.open(logo_path).convert("RGBA")
            image.thumbnail((115, 115), Image.Resampling.LANCZOS)
            window._about_logo = ctk.CTkImage(light_image=image, dark_image=image, size=image.size)
            ctk.CTkLabel(window, text="", image=window._about_logo).pack(pady=(20, 5))
        ctk.CTkLabel(window, text="CuadrantO", font=ctk.CTkFont(size=25, weight="bold")).pack()
        ctk.CTkLabel(window, text=f"Versión {__version__}", text_color="gray").pack(pady=(2, 15))
        description = (
            "Aplicación de código abierto para planificar turnos y comprobar la cobertura de los servicios.\n\n"
            "Programado por Davilah.\n\n"
            "CuadrantO no recopila, analiza ni envía al desarrollador datos personales, cuadrantes, empleados ni información de uso. "
            "Los datos se almacenan localmente. Las funciones de actualización y copia en la nube solo se conectan a GitHub y OneDrive cuando están habilitadas.\n\n"
            "Distribuido con licencia MIT."
        )
        ctk.CTkLabel(window, text=description, wraplength=540, justify="left").pack(fill="x", padx=35)
        ctk.CTkButton(window, text="Repositorio y código fuente", command=lambda: webbrowser.open("https://github.com/Davilah77/CuadrantO")).pack(pady=22)
        window.after_idle(lambda: apply_native_titlebar(window, redraw=True))
        return window

    def open_employee_manager(self):
        employee_manager(self, self.schedule.refresh_catalogues)

    def open_shift_manager(self):
        shift_manager(self, self.schedule.refresh_catalogues)

    def open_settings(self):
        window = ctk.CTkToplevel(self)
        window.title("Ajustes")
        remember_window(window, "settings", "780x760")
        window.transient(self)
        window.grab_set()
        body = ctk.CTkScrollableFrame(window, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=(18, 4))
        current = load_settings()

        def heading(text):
            ctk.CTkLabel(body, text=text, font=ctk.CTkFont(size=15, weight="bold")).pack(anchor="w", pady=(12, 5))

        heading("Identidad y visualización")
        name = ctk.StringVar(value=str(current.get("app_name", "CuadrantO")))
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
                backup.set(str(root / "CuadrantO" / "Backups"))
            else:
                messagebox.showwarning("OneDrive", "No se ha detectado una carpeta local de OneDrive.", parent=window)

        ctk.CTkButton(body, text="Detectar OneDrive", width=150, command=detect).pack(anchor="e", pady=(0, 8))

        heading("Actualizaciones")
        check_updates_on_start = ctk.BooleanVar(value=bool(current.get("check_updates_on_start", True)))
        include_prereleases = ctk.BooleanVar(value=bool(current.get("include_prereleases", True)))
        ctk.CTkSwitch(body, text="Buscar actualizaciones al iniciar", variable=check_updates_on_start).pack(anchor="w", pady=4)
        ctk.CTkSwitch(body, text="Incluir versiones beta", variable=include_prereleases).pack(anchor="w", pady=4)
        ctk.CTkLabel(body, text="La instalación siempre solicitará confirmación y creará una copia de seguridad.", text_color="gray").pack(anchor="w", pady=(0, 8))

        heading("Cobertura de trabajadores por servicio")
        coverage_mode = ctk.StringVar(value="Automático por clientes" if current.get("coverage_mode") == "automatic" else "Manual")
        mode_row = ctk.CTkFrame(body, fg_color="transparent")
        mode_row.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(mode_row, text="Modo de cálculo").pack(side="left")
        ctk.CTkOptionMenu(mode_row, variable=coverage_mode, values=["Manual", "Automático por clientes"], width=210).pack(side="right")
        ctk.CTkLabel(
            body,
            text="En automático: 1–199 clientes requieren 1 trabajador, 200–299 requieren 2, y así sucesivamente.",
            text_color="gray", wraplength=700, justify="left",
        ).pack(anchor="w", pady=(0, 8))

        automatic_frame = ctk.CTkFrame(body)
        automatic_frame.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(automatic_frame, text="Categorías que cuentan en el modo automático", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=(8, 3))
        automatic_settings = current.get("automatic_coverage", {})
        count_maitre = ctk.BooleanVar(value=bool(automatic_settings.get("count_maitre", True)))
        count_second_maitre = ctk.BooleanVar(value=bool(automatic_settings.get("count_second_maitre", True)))
        count_sector_heads = ctk.BooleanVar(value=bool(automatic_settings.get("count_sector_heads", True)))
        automatic_switches = (
            ctk.CTkSwitch(automatic_frame, text="Contar maitre", variable=count_maitre),
            ctk.CTkSwitch(automatic_frame, text="Contar segundo maitre", variable=count_second_maitre),
            ctk.CTkSwitch(automatic_frame, text="Contar jefes de sector", variable=count_sector_heads),
        )
        for switch in automatic_switches:
            switch.pack(anchor="w", padx=10, pady=3)
        ctk.CTkLabel(automatic_frame, text="Camareros y ETT se cuentan siempre.", text_color="gray").pack(anchor="w", padx=10, pady=(3, 8))

        ctk.CTkLabel(
            body,
            text="En manual, una cantidad inferior al primer nivel significa «Faltan camareros».",
            text_color="gray", wraplength=700, justify="left",
        ).pack(anchor="w", pady=(0, 8))
        coverage_vars = {}
        manual_entries = []
        manual_frame = ctk.CTkFrame(body)
        manual_frame.pack(fill="x", pady=3)
        headers = (
            "Servicio", "Faltan camareros,\nservicio viable",
            "Servicio cubierto", "Exceso de\ncamareros",
        )
        for column, label in enumerate(headers):
            manual_frame.grid_columnconfigure(column, weight=1 if column else 0)
            ctk.CTkLabel(
                manual_frame, text=label, font=ctk.CTkFont(weight="bold"),
                width=115 if column == 0 else 150,
            ).grid(row=0, column=column, padx=6, pady=(8, 4), sticky="ew")
        for row_index, service in enumerate(("desayuno", "almuerzo", "cena"), start=1):
            ctk.CTkLabel(manual_frame, text=service.title(), width=115, anchor="w").grid(
                row=row_index, column=0, padx=10, pady=5, sticky="w",
            )
            for column, key in enumerate(("yellow", "green", "purple"), start=1):
                variable = ctk.StringVar(value=str(current["coverage"][service][key]))
                coverage_vars[(service, key)] = variable
                entry = ctk.CTkEntry(manual_frame, textvariable=variable, width=70, justify="center")
                entry.grid(row=row_index, column=column, padx=8, pady=5)
                manual_entries.append(entry)

        def update_coverage_controls(*_args):
            automatic_mode = coverage_mode.get() == "Automático por clientes"
            for switch in automatic_switches:
                switch.configure(state="normal" if automatic_mode else "disabled")
            for entry in manual_entries:
                entry.configure(state="disabled" if automatic_mode else "normal")

        coverage_mode.trace_add("write", update_coverage_controls)
        update_coverage_controls()

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
                    "coverage_mode": "automatic" if coverage_mode.get() == "Automático por clientes" else "manual",
                    "automatic_coverage": {
                        "count_maitre": count_maitre.get(),
                        "count_second_maitre": count_second_maitre.get(),
                        "count_sector_heads": count_sector_heads.get(),
                    },
                    "check_updates_on_start": check_updates_on_start.get(),
                    "include_prereleases": include_prereleases.get(),
                }
                save_settings(values)
                configured_path("reports_directory").mkdir(parents=True, exist_ok=True)
                if backup_enabled.get() and backup.get().strip():
                    backup_directory().mkdir(parents=True, exist_ok=True)
                ctk.set_widget_scaling(scale)
                self._refresh_branding()
                self.schedule.apply_display_settings()
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
