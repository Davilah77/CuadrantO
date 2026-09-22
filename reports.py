from datetime import timedelta

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from core.settings import app_logo_path, configured_path, load_settings
from modules.cuadrante import DAYS, REMINDER_COLORS


STATUS_COLORS = {
    "DESCANSO": colors.HexColor("#2E8B57"),
    "PROPIO": colors.HexColor("#7D3C98"),
    "BAJA": colors.HexColor("#C0392B"),
    "FALTA": colors.HexColor("#E67E22"),
}


def export_schedule_pdf(module, monday):
    settings = load_settings()
    output_dir = configured_path("reports_directory")
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"cuadrante_{monday:%Y-%m-%d}.pdf"
    document = SimpleDocTemplate(
        str(output), pagesize=landscape(A4), leftMargin=9 * mm, rightMargin=9 * mm,
        topMargin=8 * mm, bottomMargin=8 * mm,
    )
    story = []
    logo_path = app_logo_path()
    if logo_path.is_file():
        story.append(Image(str(logo_path), width=18 * mm, height=18 * mm, kind="proportional"))
    title_style = ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=15, alignment=TA_CENTER, spaceAfter=4)
    story.append(Paragraph(str(settings.get("app_name") or "CuadrantO"), title_style))
    story.append(Paragraph(f"Cuadrante del {monday:%d/%m/%Y} al {(monday + timedelta(days=6)):%d/%m/%Y}", title_style))
    story.append(Spacer(1, 3 * mm))

    headers = ["Empleado"] + [f"{day}<br/>{(monday + timedelta(days=i)):%d/%m}" for i, day in enumerate(DAYS)]
    data = [[Paragraph(value, ParagraphStyle("head", fontName="Helvetica-Bold", fontSize=8, alignment=TA_CENTER)) for value in headers]]
    categories = []
    employee_rows = {}
    for employee in module.employees:
        if employee["categoria"] not in categories:
            categories.append(employee["categoria"])
            data.append([employee["categoria"]] + [""] * 7)
        data.append([employee["nombre"]] + [module.assignment_vars[(employee["id"], day)].get() or "—" for day in range(7)])
        employee_rows[employee["id"]] = len(data) - 1
    data.append(["CLIENTES"] + [""] * 7)
    for service in ("desayuno", "almuerzo", "cena", "todo_incluido"):
        data.append([service.replace("_", " ").upper()] + [module.client_vars[(service, day)].get() for day in range(7)])
    data.append(["TRABAJADORES"] + [""] * 7)
    for service in ("desayuno", "almuerzo", "cena"):
        data.append([service.upper()] + [module.coverage_labels[(service, day)].cget("text") for day in range(7)])
    data.append(["APERTURA"] + [module.opening_labels[day].cget("text") for day in range(7)])
    data.append(["GUARDIA"] + [module.guard_labels[day].cget("text") for day in range(7)])

    table = Table(data, colWidths=[54 * mm] + [30 * mm] * 7, repeatRows=1)
    style = [
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F4E84A")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F5F5")]),
    ]
    category_rows = [index for index, row in enumerate(data) if row[0] in categories or row[0] in ("CLIENTES", "TRABAJADORES")]
    for row in category_rows:
        style.extend([("SPAN", (0, row), (-1, row)), ("BACKGROUND", (0, row), (-1, row), colors.HexColor("#F4E84A")), ("FONTNAME", (0, row), (-1, row), "Helvetica-Bold")])
    employee_start = 1
    for row_index, row in enumerate(data):
        if row_index <= employee_start:
            continue
        for column in range(1, 8):
            color = STATUS_COLORS.get(str(row[column]))
            if color:
                style.extend([("BACKGROUND", (column, row_index), (column, row_index), color), ("TEXTCOLOR", (column, row_index), (column, row_index), colors.white)])
    for (employee_id, day_index), reminder in module.reminders.items():
        if employee_id in employee_rows and reminder["color"] in REMINDER_COLORS:
            reminder_color = colors.HexColor(REMINDER_COLORS[reminder["color"]][0])
            style.extend([
                ("BACKGROUND", (day_index + 1, employee_rows[employee_id]), (day_index + 1, employee_rows[employee_id]), reminder_color),
                ("TEXTCOLOR", (day_index + 1, employee_rows[employee_id]), (day_index + 1, employee_rows[employee_id]), colors.white),
            ])
    opening_row = len(data) - 2
    style.extend([("BACKGROUND", (0, opening_row), (-1, opening_row), colors.HexColor("#B8E33D")), ("FONTNAME", (0, opening_row), (-1, opening_row), "Helvetica-Bold")])
    guard_row = len(data) - 1
    style.extend([("BACKGROUND", (0, guard_row), (-1, guard_row), colors.HexColor("#B9D7EA")), ("FONTNAME", (0, guard_row), (-1, guard_row), "Helvetica-Bold")])
    table.setStyle(TableStyle(style))
    story.append(table)
    reminders = []
    employee_names = {row["id"]: row["nombre"] for row in module.employees}
    for (employee_id, day_index), reminder in sorted(module.reminders.items(), key=lambda item: (item[0][1], item[0][0])):
        reminders.append(f'<b>{DAYS[day_index]} · {employee_names[employee_id]}:</b> {reminder["nota"] or "Aviso especial"}')
    if reminders:
        story.append(Spacer(1, 3 * mm))
        story.append(Paragraph("Recordatorios especiales", ParagraphStyle("reminder-title", fontName="Helvetica-Bold", fontSize=9)))
        for reminder in reminders:
            story.append(Paragraph(reminder, ParagraphStyle("reminder", fontName="Helvetica", fontSize=8, leading=10)))
    document.build(story)
    return output
