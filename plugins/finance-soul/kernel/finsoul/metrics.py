"""Unit economics and cash metrics derived from evaluated model lines.

Anything undefined (division by zero, no sign change, never happens) is None,
with a warning, never inf or a crash.
"""
from typing import Dict, List, Optional

from .inputs import ModelInputs
from .tvm import irr, npv, payback_period

LTV_CAC_MIN = 3.0
CAC_PAYBACK_MAX_MONTHS = 12


def _div(a: float, b: float) -> Optional[float]:
    return None if b == 0 else a / b


def unit_economics(mi: ModelInputs, values: Dict[str, List[float]]) -> dict:
    sc = mi.scenarios[mi.scenario]
    warnings: List[str] = []
    s0 = mi.revenue_streams[0]
    price = s0.price * sc.price
    contribution = price - s0.variable_cost * sc.variable_costs

    total_revenue = sum(values["revenue"])
    total_units = sum(sum(values["units_%d" % i]) for i in range(len(mi.revenue_streams)))
    total_gp = sum(values["gross_profit"])
    weighted_margin = _div(total_gp, total_revenue)
    if weighted_margin is None:
        warnings.append("выручка за горизонт нулевая — маржинальность не определена")
    weighted_contribution = _div(total_gp, total_units) if total_units else contribution

    breakeven = None
    fixed_first = values["fixed_costs"][0]
    if weighted_contribution is not None and weighted_contribution > 0:
        breakeven = fixed_first / weighted_contribution
    else:
        warnings.append("маржинальный доход на единицу ≤ 0 — безубыточность недостижима")

    capacity = s0.capacity
    breakeven_above_capacity = bool(
        breakeven is not None and capacity is not None and len(mi.revenue_streams) == 1
        and breakeven > capacity
    )

    ue_in = mi.unit_economics
    ltv = None
    if ue_in.churn_monthly:
        ltv = contribution / ue_in.churn_monthly if contribution > 0 else None
    else:
        warnings.append("отток не задан или равен 0 — LTV не определён")
    ltv_cac = _div(ltv, ue_in.cac) if (ltv is not None and ue_in.cac) else None
    cac_payback = _div(ue_in.cac, contribution) if (ue_in.cac and contribution > 0) else None

    return {
        "unit": s0.unit,
        "price": price,
        "contribution_per_unit": contribution,
        "contribution_margin": _div(contribution, price),
        "contribution_margin_weighted": weighted_margin,
        "breakeven_units_per_month": breakeven,
        "breakeven_above_capacity": breakeven_above_capacity,
        "capacity": capacity,
        "cac": ue_in.cac,
        "churn_monthly": ue_in.churn_monthly,
        "ltv": ltv,
        "ltv_cac": ltv_cac,
        "cac_payback_months": cac_payback,
        "warnings": warnings,
    }


def _first(pred, seq) -> Optional[int]:
    for i, v in enumerate(seq):
        if pred(v):
            return i
    return None


def cash_metrics(mi: ModelInputs, values: Dict[str, List[float]]) -> dict:
    cash = values["cash"]
    fcf = [o + i for o, i in zip(values["cf_operating"], values["cf_investing"])]

    before_financing = []
    running = mi.opening_cash
    for f in fcf:
        running += f
        before_financing.append(running)

    min_cash = min(cash)
    first_negative = _first(lambda v: v < 0, cash)
    breakeven = _first(lambda v: v > 0, values["ebitda"])

    monthly = (1 + mi.discount_rate_annual) ** (1 / 12) - 1
    irr_m = irr(fcf)
    payback = payback_period(fcf)
    return {
        "min_cash": min_cash,
        "min_cash_month": cash.index(min_cash) + 1,
        "first_negative_cash_month": None if first_negative is None else first_negative + 1,
        "runway_months": first_negative,  # full months covered before cash goes negative
        "peak_funding_need": max(0.0, -min(before_financing)),
        "breakeven_month": None if breakeven is None else breakeven + 1,
        "fcf": fcf,
        "npv_fcf": npv(monthly, fcf),
        "irr_fcf": None if irr_m is None else (1 + irr_m) ** 12 - 1,
        "payback_month": None if payback is None else payback + 1,
        "discount_rate_annual": mi.discount_rate_annual,
    }


def metric_checks(ue: dict, cm: dict) -> List[dict]:
    out: List[dict] = []

    def warn(id_: str, message: str, period: Optional[int] = None) -> None:
        out.append({"id": id_, "level": "warning", "message": message, "period": period})

    if cm["first_negative_cash_month"] is not None:
        m = cm["first_negative_cash_month"]
        warn("negative_cash", "деньги уходят в минус в месяце %d — нужно финансирование, минимум %.0f"
             % (m, -cm["min_cash"]), m - 1)
    if ue["contribution_per_unit"] <= 0:
        warn("price_below_variable_cost", "цена не покрывает переменные затраты на единицу")
    if ue["breakeven_above_capacity"]:
        warn("breakeven_above_capacity", "точка безубыточности (%.0f в месяц) выше мощности (%.0f)"
             % (ue["breakeven_units_per_month"], ue["capacity"]))
    if ue["ltv_cac"] is not None and ue["ltv_cac"] < LTV_CAC_MIN:
        warn("ltv_cac_below_3", "LTV/CAC = %.1f — ниже ориентира %.0f" % (ue["ltv_cac"], LTV_CAC_MIN))
    if ue["cac_payback_months"] is not None and ue["cac_payback_months"] > CAC_PAYBACK_MAX_MONTHS:
        warn("cac_payback_over_12", "окупаемость CAC %.1f мес. — дольше %d"
             % (ue["cac_payback_months"], CAC_PAYBACK_MAX_MONTHS))
    for w in ue["warnings"]:
        warn("unit_economics_note", w)
    return out
