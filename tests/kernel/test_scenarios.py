import json
from pathlib import Path

import pytest

from finsoul.inputs import parse_inputs
from finsoul.scenarios import run_scenarios, sensitivity

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "edtech_inputs.json"


@pytest.fixture(scope="module")
def mi():
    return parse_inputs(json.loads(FIXTURE.read_text(encoding="utf-8")))


def test_three_scenarios_ordered(mi):
    res = run_scenarios(mi)
    assert set(res) == {"base", "upside", "downside"}
    total = {k: sum(r["values"]["revenue"]) for k, r in res.items()}
    assert total["downside"] < total["base"] < total["upside"]
    for r in res.values():
        assert max(abs(x) for x in r["values"]["balance_diff"]) < 0.5
        assert set(r) >= {"values", "unit_economics", "cash_metrics", "checks"}


def test_run_scenarios_does_not_mutate_inputs(mi):
    run_scenarios(mi)
    assert mi.scenario == "base"


def test_sensitivity_sorted_by_swing(mi):
    rows = sensitivity(mi)
    assert [r["driver"] for r in rows] and len(rows) == 4
    swings = [abs(r["high"] - r["low"]) for r in rows]
    assert swings == sorted(swings, reverse=True)
    price = next(r for r in rows if r["driver"] == "price")
    assert price["high"] > price["low"]
    fixed = next(r for r in rows if r["driver"] == "fixed_costs")
    assert fixed["high"] < fixed["low"]  # higher costs, lower NPV
