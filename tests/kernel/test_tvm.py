import pytest

from finsoul.tvm import (
    annuity_payment, discounted_payback, irr, monthly_rate, npv, payback_period,
)


def test_npv_first_flow_undiscounted():
    assert npv(0.1, [-100, 60, 60]) == pytest.approx(4.1322, abs=1e-4)


def test_irr_known_value():
    assert irr([-100, 60, 60]) == pytest.approx(0.130662, abs=1e-6)


def test_irr_none_without_sign_change():
    assert irr([100, 50]) is None
    assert irr([-100, -50]) is None
    assert irr([]) is None


def test_payback_interpolates():
    assert payback_period([-100, 40, 40, 40]) == pytest.approx(2.5)


def test_payback_none_when_never_recovered():
    assert payback_period([-100, 10, 10]) is None


def test_discounted_payback_longer_than_simple():
    flows = [-100, 40, 40, 40, 40]
    assert discounted_payback(0.1, flows) > payback_period(flows)
    assert discounted_payback(0.5, [-100, 40, 40]) is None


def test_annuity_payment():
    assert annuity_payment(0.01, 12, 1_000_000) == pytest.approx(88848.79, abs=0.01)
    assert annuity_payment(0.0, 12, 1200) == pytest.approx(100)


def test_monthly_rate_nominal():
    assert monthly_rate(0.24) == pytest.approx(0.02)
