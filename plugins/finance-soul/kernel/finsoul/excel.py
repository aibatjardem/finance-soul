"""Workbook with live formulas, rendered from the same graph the kernel evaluates."""
from typing import Dict, List

from .graph import INPUT_SHEET, MODEL_SHEET, Ctx, Layout, col_letter

CHECKS_SHEET = "Проверки"
SECTIONS = [
    ("drivers", "Драйверы (активный сценарий)"),
    ("pl", "Отчёт о прибылях и убытках"),
    ("cf", "Движение денежных средств"),
    ("bs", "Баланс"),
    ("check", "Проверка"),
]
FORMATS = {"money": "#,##0", "pct": "0.0%", "num": "#,##0.00"}
BLUE = "FF0000FF"


def month_labels(start: str, n: int) -> List[str]:
    year, month = (int(x) for x in start.split("-"))
    out = []
    for _ in range(n):
        out.append("%04d-%02d" % (year, month))
        month += 1
        if month > 12:
            year, month = year + 1, 1
    return out


def section_layout(ctx: Ctx) -> Layout:
    """Inputs as in the default layout; model lines grouped under section headers."""
    base = Layout.default(ctx)
    rows: Dict[str, int] = {}
    row = 2
    for key, _ in SECTIONS:
        names = [n for n, ln in ctx.lines.items() if ln.section == key]
        if not names:
            continue
        row += 1  # section header
        for name in names:
            rows[name] = row
            row += 1
        row += 1  # blank line between sections
    return Layout(base.input_rows, base.series_rows, rows)


def write_xlsx(ctx: Ctx, path: str, checks: List[dict]) -> None:
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font
        from openpyxl.worksheet.datavalidation import DataValidation
    except ImportError:
        raise RuntimeError("Нужен openpyxl: python3 -m pip install --user openpyxl")

    ctx.layout = section_layout(ctx)
    lay = ctx.layout
    mi = ctx.meta.get("inputs")
    labels = month_labels(mi.start, ctx.periods) if mi else ["M%d" % (t + 1) for t in range(ctx.periods)]
    bold, blue = Font(bold=True), Font(color=BLUE)

    wb = Workbook()
    wi = wb.active
    wi.title = INPUT_SHEET
    wi["A1"], wi["B1"], wi["C1"] = "Ключ", "Параметр", "Значение"
    for c in ("A1", "B1", "C1"):
        wi[c].font = bold
    for name, row in lay.input_rows.items():
        wi.cell(row=row, column=1, value=name)
        wi.cell(row=row, column=2, value=ctx.labels.get(name, name))
        cell = wi.cell(row=row, column=3, value=ctx.inputs[name])
        cell.font = blue
    sel_row = lay.input_rows["scenario_index"]
    dv = DataValidation(type="list", formula1='"1,2,3"', allow_blank=False)
    wi.add_data_validation(dv)
    dv.add("C%d" % sel_row)

    if lay.series_rows:
        header = min(lay.series_rows.values()) - 1
        wi.cell(row=header, column=2, value="Входные ряды по месяцам").font = bold
        for t, label in enumerate(labels):
            wi.cell(row=header, column=lay.series_first_col + t, value=label).font = bold
        for name, row in lay.series_rows.items():
            wi.cell(row=row, column=1, value=name)
            wi.cell(row=row, column=2, value=ctx.labels.get(name, name))
            for t, v in enumerate(ctx.series[name]):
                c = wi.cell(row=row, column=lay.series_first_col + t, value=v)
                c.font = blue
                c.number_format = FORMATS["money"]
    wi.column_dimensions["A"].width = 22
    wi.column_dimensions["B"].width = 60
    wi.column_dimensions["C"].width = 16
    wi.freeze_panes = "C2"

    wm = wb.create_sheet(MODEL_SHEET)
    wm["A1"] = "Строка"
    wm["A1"].font = bold
    for t, label in enumerate(labels):
        wm.cell(row=1, column=lay.line_first_col + t, value=label).font = bold
    for key, title in SECTIONS:
        names = [n for n, ln in ctx.lines.items() if ln.section == key]
        if names:
            wm.cell(row=lay.line_rows[names[0]] - 1, column=1, value=title).font = bold
    for name, line in ctx.lines.items():
        row = lay.line_rows[name]
        wm.cell(row=row, column=1, value=line.label)
        for t in range(ctx.periods):
            c = wm.cell(row=row, column=lay.line_first_col + t, value="=" + line.expr.to_excel(ctx, t))
            c.number_format = FORMATS.get(line.fmt, FORMATS["money"])
    wm.column_dimensions["A"].width = 48
    wm.freeze_panes = "B2"

    wc = wb.create_sheet(CHECKS_SHEET)
    diff_row = lay.line_rows["balance_diff"]
    first = col_letter(lay.line_first_col)
    last = col_letter(lay.line_first_col + ctx.periods - 1)
    wc["A1"], wc["A1"].font = "Проверка", bold
    wc["A2"] = "Максимум (активы − пассивы) за горизонт — должно быть 0"
    wc["B2"] = "=MAX('%s'!%s%d:%s%d)" % (MODEL_SHEET, first, diff_row, last, diff_row)
    wc["A3"] = "Минимум (активы − пассивы) за горизонт — должно быть 0"
    wc["B3"] = "=MIN('%s'!%s%d:%s%d)" % (MODEL_SHEET, first, diff_row, last, diff_row)
    wc["A5"], wc["A5"].font = "Замечания ядра (для сценария на момент выгрузки)", bold
    for i, ch in enumerate(checks):
        wc.cell(row=6 + i, column=1, value="%s [%s]" % (ch["message"], ch["level"]))
    wc.column_dimensions["A"].width = 90

    wb.save(path)
