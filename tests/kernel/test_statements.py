import json
from pathlib import Path

import pytest

from finsoul.checks import run_checks
from finsoul.graph import evaluate
from finsoul.inputs import parse_inputs
from finsoul.statements import REQUIRED_LINES, build_model

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "edtech_inputs.json"


def edtech_raw():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def run(raw):
    ctx = build_model(parse_inputs(raw))
    return ctx, evaluate(ctx)


@pytest.fixture(scope="module")
def edtech():
    return run(edtech_raw())


def mini(**over):
    raw = {
        "name": "mini", "start": "2027-01", "months": 3,
        "revenue_streams": [{"name": "s", "price": 1, "variable_cost": 0, "ramp": [0, 160, 160]}],
        "fixed_costs": [{"name": "f", "monthly": 100}],
        "tax": {"cit_rate": 0.2, "source": "test"},
    }
    raw.update(over)
    return raw


def test_required_lines_present(edtech):
    ctx, values = edtech
    for name in REQUIRED_LINES:
        assert name in values, name


def test_balance_balances_every_month(edtech):
    _, values = edtech
    assert max(abs(x) for x in values["balance_diff"]) < 0.5


def test_cash_ties_to_cash_flow(edtech):
    _, v = edtech
    assert v["cash"][0] == pytest.approx(0 + v["net_cash_flow"][0])
    for t in range(1, 36):
        assert v["cash"][t] == pytest.approx(v["cash"][t - 1] + v["net_cash_flow"][t])


def test_retained_earnings_rollforward(edtech):
    _, v = edtech
    for t in range(1, 36):
        assert v["retained_earnings"][t] == pytest.approx(v["retained_earnings"][t - 1] + v["net_income"][t])


def test_month1_revenue(edtech):
    _, v = edtech
    assert v["revenue"][0] == pytest.approx(40 * 25000)


def test_volume_grows_after_ramp_and_caps(edtech):
    _, v = edtech
    assert v["revenue"][6] == pytest.approx(230 * 1.05 * 25000)
    assert max(v["revenue"]) <= 2000 * 25000 + 0.01


def test_fixed_costs_step_growth(edtech):
    _, v = edtech
    month1 = 4_500_000 + 600_000 + 1_500_000 + 300_000
    assert v["fixed_costs"][0] == pytest.approx(month1)
    assert v["fixed_costs"][12] == pytest.approx(month1 + 450_000)


def test_loss_carryforward():
    _, v = run(mini())
    assert v["ebt"] == pytest.approx([-100, 60, 60])
    assert v["tax"] == pytest.approx([0, 0, 4])


def test_depreciation_linear(edtech):
    _, v = edtech
    assert v["depreciation"][0] == 0
    assert v["depreciation"][1] == pytest.approx(6_000_000 / 36)


def test_loan_interest_and_repayment(edtech):
    _, v = edtech
    assert v["debt"][1] == 0
    assert v["debt"][2] == pytest.approx(30_000_000)
    assert v["interest"][3] == pytest.approx(30_000_000 * 0.22 / 12)
    assert v["debt"][2 + 24] == pytest.approx(0, abs=0.01)


def test_scenario_switch_changes_revenue():
    raw = edtech_raw()
    raw["scenario"] = "downside"
    _, v = run(raw)
    assert v["revenue"][0] == pytest.approx(40 * 0.8 * 25000 * 0.9)


def test_balance_holds_in_every_scenario():
    for name in ("base", "upside", "downside"):
        raw = edtech_raw()
        raw["scenario"] = name
        _, v = run(raw)
        assert max(abs(x) for x in v["balance_diff"]) < 0.5, name


def test_run_checks_clean(edtech):
    ctx, values = edtech
    assert [c for c in run_checks(ctx, values) if c["level"] == "error"] == []


def test_run_checks_flags_imbalance(edtech):
    ctx, values = edtech
    broken = dict(values)
    broken["balance_diff"] = list(values["balance_diff"])
    broken["balance_diff"][5] = 10
    errors = [c for c in run_checks(ctx, broken) if c["level"] == "error"]
    assert errors and errors[0]["period"] == 5


def test_balance_tolerance_scales_with_size(edtech):
    ctx, values = edtech
    big = dict(values)
    big["balance_diff"] = list(values["balance_diff"])
    big["total_assets"] = list(values["total_assets"])
    big["balance_diff"][5] = 1.0
    big["total_assets"][5] = 1e12
    assert [c for c in run_checks(ctx, big) if c["id"] == "balance_mismatch"] == []
