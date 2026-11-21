import copy
import json
from pathlib import Path

import pytest

from finsoul.inputs import InputError, load_inputs, parse_inputs

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "edtech_inputs.json"


def raw():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def errors_of(data):
    with pytest.raises(InputError) as exc:
        parse_inputs(data)
    return exc.value.all


def test_loads_edtech_fixture():
    mi = load_inputs(str(FIXTURE))
    assert mi.months == 36
    assert mi.currency == "KZT"
    assert mi.revenue_streams[0].price == 25000
    assert mi.financing.loans[0].term_months == 24
    assert mi.scenarios["downside"].volume == 0.8


def test_defaults_applied():
    data = raw()
    del data["scenarios"], data["working_capital"], data["currency"]
    mi = parse_inputs(data)
    assert mi.currency == "KZT"
    assert mi.working_capital.dso_days == 0
    assert mi.scenarios["upside"].volume == 1.2
    assert mi.scenarios["downside"].variable_costs == 1.15


def test_missing_price_reports_path():
    data = raw()
    del data["revenue_streams"][0]["price"]
    errs = errors_of(data)
    assert errs[0].path == "revenue_streams[0].price"
    assert "обязательное" in errs[0].message


def test_collects_all_errors():
    data = raw()
    data["months"] = "много"
    data["revenue_streams"][0]["ramp"] = []
    errs = errors_of(data)
    assert len(errs) == 2
    assert {e.path for e in errs} == {"months", "revenue_streams[0].ramp"}


def test_unknown_scenario():
    data = raw()
    data["scenario"] = "best"
    errs = errors_of(data)
    assert errs[0].path == "scenario"
    assert "downside" in errs[0].message


def test_tax_source_required():
    data = raw()
    del data["tax"]["source"]
    errs = errors_of(data)
    assert errs[0].path == "tax.source"


def test_unknown_top_level_key_is_error():
    data = raw()
    data["revnue_streams"] = data["revenue_streams"]
    errs = errors_of(data)
    assert errs[0].path == "revnue_streams"
    assert "revenue_streams" in errs[0].message


def test_month_outside_horizon():
    data = raw()
    data["capex"][0]["month"] = 40
    errs = errors_of(data)
    assert errs[0].path == "capex[0].month"


def test_negative_price_rejected():
    data = raw()
    data["revenue_streams"][0]["price"] = -5
    assert errors_of(data)[0].path == "revenue_streams[0].price"


def test_bool_is_not_a_number():
    data = raw()
    data["months"] = True
    assert errors_of(data)[0].path == "months"


def test_fx_block_ignored():
    data = raw()
    data["fx"] = {"USD": 500}
    assert parse_inputs(data).fx == {"USD": 500}


def test_invalid_json_file(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{ nope", encoding="utf-8")
    with pytest.raises(InputError) as exc:
        load_inputs(str(p))
    assert "JSON" in exc.value.message


def test_growth_monthly_capped():
    data = raw()
    data["revenue_streams"][0]["growth_monthly"] = 1000
    assert errors_of(data)[0].path == "revenue_streams[0].growth_monthly"
