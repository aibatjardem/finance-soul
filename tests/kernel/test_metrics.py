import json
from pathlib import Path

import pytest

from finsoul.graph import evaluate
from finsoul.inputs import parse_inputs
from finsoul.metrics import cash_metrics, metric_checks, unit_economics
from finsoul.statements import build_model

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "edtech_inputs.json"


def raw():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def compute(data):
    mi = parse_inputs(data)
    values = evaluate(build_model(mi))
    ue = unit_economics(mi, values)
    cm = cash_metrics(mi, values)
    return mi, values, ue, cm


def ids(checks):
    return {c["id"] for c in checks}


def test_contribution():
    _, _, ue, _ = compute(raw())
    assert ue["contribution_per_unit"] == pytest.approx(22000)
    assert ue["contribution_margin"] == pytest.approx(0.88)


def test_ltv_and_ratio():
    _, _, ue, _ = compute(raw())
    assert ue["ltv"] == pytest.approx(22000 / 0.06)
    assert ue["ltv_cac"] == pytest.approx((22000 / 0.06) / 18000)
    assert ue["cac_payback_months"] == pytest.approx(18000 / 22000)


def test_breakeven_units():
    _, _, ue, _ = compute(raw())
    assert ue["breakeven_units_per_month"] == pytest.approx(6_900_000 / 22000)


def test_zero_churn_gives_none():
    data = raw()
    data["unit_economics"]["churn_monthly"] = 0
    _, _, ue, _ = compute(data)
    assert ue["ltv"] is None and ue["ltv_cac"] is None
    assert any("отток" in w for w in ue["warnings"])


def test_negative_contribution():
    data = raw()
    data["revenue_streams"][0]["price"] = 1000
    _, _, ue, cm = compute(data)
    assert ue["breakeven_units_per_month"] is None
    assert "price_below_variable_cost" in ids(metric_checks(ue, cm))


def test_breakeven_above_capacity():
    data = raw()
    data["revenue_streams"][0]["capacity"] = 100
    _, _, ue, cm = compute(data)
    assert "breakeven_above_capacity" in ids(metric_checks(ue, cm))


def test_negative_cash_warning():
    data = raw()
    data["financing"] = {}
    _, _, ue, cm = compute(data)
    checks = metric_checks(ue, cm)
    neg = [c for c in checks if c["id"] == "negative_cash"]
    assert neg and neg[0]["level"] == "warning" and isinstance(neg[0]["period"], int)
    assert cm["peak_funding_need"] > 0
    assert isinstance(cm["runway_months"], int)


def test_funded_model_has_no_runway_limit():
    _, values, _, cm = compute(raw())
    if min(values["cash"]) >= 0:
        assert cm["runway_months"] is None
    assert cm["peak_funding_need"] > 0  # the business burns cash before financing
    assert cm["breakeven_month"] is not None


def test_irr_none_when_never_positive():
    data = raw()
    data["revenue_streams"][0]["price"] = 3000
    _, _, _, cm = compute(data)
    assert cm["irr_fcf"] is None


def test_zero_revenue_does_not_crash():
    data = raw()
    data["revenue_streams"][0]["ramp"] = [0]
    data["revenue_streams"][0]["growth_monthly"] = 0
    _, _, ue, cm = compute(data)
    assert ue["contribution_margin_weighted"] is None
    assert cm["breakeven_month"] is None


def test_breakeven_counts_costs_that_start_later():
    data = raw()
    for f in data["fixed_costs"]:
        f["start_month"] = 2
    _, _, ue, _ = compute(data)
    assert ue["breakeven_units_per_month"] == pytest.approx(6_900_000 / 22000)
