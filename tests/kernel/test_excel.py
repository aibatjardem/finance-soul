import json
from pathlib import Path

import openpyxl
import pytest
from pycel import ExcelCompiler

from finsoul.excel import MODEL_SHEET, INPUT_SHEET, write_xlsx
from finsoul.inputs import parse_inputs
from finsoul.scenarios import run_one, run_scenarios

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "edtech_inputs.json"
KEY_LINES = ["revenue", "net_income", "cash", "balance_diff", "tax", "debt"]
MONTHS = [0, 11, 35]


@pytest.fixture(scope="module")
def mi():
    return parse_inputs(json.loads(FIXTURE.read_text(encoding="utf-8")))


@pytest.fixture(scope="module")
def workbook(mi, tmp_path_factory):
    res = run_one(mi)
    path = tmp_path_factory.mktemp("x") / "model.xlsx"
    write_xlsx(res["ctx"], str(path), res["checks"])
    return res, path


def cell_of(ctx, name, t):
    row, col = ctx.layout.line_cell(name, t)
    return row, col


def test_formulas_not_hardcoded(workbook):
    res, path = workbook
    ctx = res["ctx"]
    ws = openpyxl.load_workbook(path)[MODEL_SHEET]
    for name in ctx.lines:
        for t in range(ctx.periods):
            row, col = cell_of(ctx, name, t)
            v = ws.cell(row=row, column=col).value
            assert isinstance(v, str) and v.startswith("="), (name, t, v)


def _compare(ctx, values, path):
    xl = ExcelCompiler(filename=str(path))
    for name in KEY_LINES:
        for t in MONTHS:
            addr = ctx.layout.line_addr(name, t).replace("'", "")
            assert xl.evaluate(addr) == pytest.approx(values[name][t], abs=0.01), (name, t)


def test_pycel_matches_kernel_base(workbook):
    res, path = workbook
    _compare(res["ctx"], res["values"], path)


def test_pycel_matches_kernel_downside(mi, workbook, tmp_path):
    res, path = workbook
    ctx = res["ctx"]
    wb = openpyxl.load_workbook(path)
    wb[INPUT_SHEET].cell(row=ctx.layout.input_rows["scenario_index"], column=3).value = 3
    switched = tmp_path / "downside.xlsx"
    wb.save(switched)
    downside = run_scenarios(mi)["downside"]["values"]
    _compare(ctx, downside, switched)


def test_sheets_and_checks_present(workbook):
    _, path = workbook
    wb = openpyxl.load_workbook(path)
    assert wb.sheetnames == [INPUT_SHEET, MODEL_SHEET, "Проверки"]
