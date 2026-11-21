"""Linked P&L, balance sheet and cash flow, built as graph lines.

Simplifications of v0.1 (the report states them):
- VAT is pass-through: inputs are net of VAT and VAT does not touch the balance sheet.
- Corporate income tax is paid in the month it accrues; losses carry forward.
- Opening cash is treated as owner's equity paid in before month 1.
- Loan schedules are fixed annuities computed by the kernel and placed on the inputs sheet;
  they do not depend on the scenario.
"""
from typing import Dict, List

from .graph import Ctx, Expr, Input, Line, Max, Min, Pick, Ref, Series, Sum, wrap
from .inputs import DRIVERS, SCENARIO_NAMES, ModelInputs
from .tvm import annuity_schedule, monthly_rate

REQUIRED_LINES = [
    "revenue", "variable_costs", "gross_profit", "fixed_costs", "ebitda", "depreciation", "ebit",
    "interest", "ebt", "tax_loss_pool", "taxable_income", "tax", "net_income",
    "cash", "receivables", "fixed_assets_net", "total_assets", "payables", "debt", "equity_paid",
    "retained_earnings", "total_liabilities_equity",
    "cf_operating", "cf_investing", "cf_financing", "net_cash_flow", "balance_diff",
]

DRIVER_LABELS = {
    "price": "цена", "volume": "объём", "variable_costs": "переменные затраты",
    "fixed_costs": "постоянные затраты",
}
SCENARIO_LABELS = {"base": "базовый", "upside": "оптимистичный", "downside": "пессимистичный"}


def stream_volumes(stream, months: int) -> List[float]:
    """Volume before scenario multiplier and capacity: the ramp, then monthly growth."""
    ramp = stream.ramp
    out = []
    for t in range(months):
        if t < len(ramp):
            out.append(float(ramp[t]))
        else:
            out.append(ramp[-1] * (1 + stream.growth_monthly) ** (t - len(ramp) + 1))
    return out


def fixed_cost_series(cost, months: int) -> List[float]:
    """Monthly amount from start_month, stepping up by growth_annual every 12 months
    of the model."""
    return [
        0.0 if t < cost.start_month - 1 else cost.monthly * (1 + cost.growth_annual) ** (t // 12)
        for t in range(months)
    ]


def _add(exprs: List[Expr]) -> Expr:
    if not exprs:
        return wrap(0)
    total = exprs[0]
    for e in exprs[1:]:
        total = total + e
    return total


def build_model(mi: ModelInputs) -> Ctx:
    n = mi.months
    inputs: Dict[str, float] = {}
    labels: Dict[str, str] = {}
    series: Dict[str, List[float]] = {}

    def add_input(name: str, value: float, label: str) -> None:
        inputs[name] = float(value)
        labels[name] = label

    def add_series(name: str, values: List[float], label: str) -> None:
        series[name] = [float(v) for v in values]
        labels[name] = label

    add_input("scenario_index", mi.scenario_index, "Сценарий: 1 базовый, 2 оптимистичный, 3 пессимистичный")
    for sc in SCENARIO_NAMES:
        for drv in DRIVERS:
            add_input("%s_%s" % (sc, drv), getattr(mi.scenarios[sc], drv),
                      "Множитель «%s», сценарий %s" % (DRIVER_LABELS[drv], SCENARIO_LABELS[sc]))
    add_input("cit_rate", mi.tax.cit_rate, "Ставка КПН (%s)" % (mi.tax.source or "источник не указан"))
    add_input("dso_days", mi.working_capital.dso_days, "Дебиторка, дней выручки")
    add_input("dpo_days", mi.working_capital.dpo_days, "Кредиторка, дней затрат")
    add_input("opening_cash", mi.opening_cash, "Деньги на начало, %s" % mi.currency)
    for i, s in enumerate(mi.revenue_streams):
        add_input("price_%d" % i, s.price, "Цена: %s, %s за %s" % (s.name, mi.currency, s.unit))
        add_input("variable_cost_%d" % i, s.variable_cost, "Переменные затраты на единицу: %s" % s.name)
        if s.capacity is not None:
            add_input("capacity_%d" % i, s.capacity, "Мощность в месяц: %s, %s" % (s.name, s.unit))

    for i, s in enumerate(mi.revenue_streams):
        add_series("volume_%d" % i, stream_volumes(s, n), "Объём до сценария: %s, %s" % (s.name, s.unit))
    for j, c in enumerate(mi.fixed_costs):
        add_series("fixed_%d" % j, fixed_cost_series(c, n), "Постоянные: %s" % c.name)

    capex = [0.0] * n
    depreciation = [0.0] * n
    for c in mi.capex:
        t0 = c.month - 1
        capex[t0] += c.amount
        for k in range(c.life_months):
            if t0 + 1 + k < n:
                depreciation[t0 + 1 + k] += c.amount / c.life_months
    add_series("capex_spend", capex, "Капвложения")
    add_series("depreciation_plan", depreciation, "Амортизация (линейная, с месяца после покупки)")

    equity_in = [0.0] * n
    for e in mi.financing.equity:
        equity_in[e.month - 1] += e.amount
    add_series("equity_in", equity_in, "Взносы в капитал")

    draw = [0.0] * n
    principal = [0.0] * n
    interest = [0.0] * n
    for ln in mi.financing.loans:
        t0 = ln.month - 1
        draw[t0] += ln.amount
        for k, row in enumerate(annuity_schedule(monthly_rate(ln.rate_annual), ln.term_months, ln.amount)):
            t = t0 + 1 + k
            if t < n:
                principal[t] += row["principal"]
                interest[t] += row["interest"]
    add_series("loan_draw", draw, "Получение кредитов")
    add_series("loan_principal", principal, "Погашение тела кредитов (аннуитет)")
    add_series("loan_interest", interest, "Проценты по кредитам")

    sel = Input("scenario_index")

    def driver(drv: str) -> Expr:
        return Pick(sel, [Input("%s_%s" % (sc, drv)) for sc in SCENARIO_NAMES])

    lines: List[Line] = [
        Line("price_mult", "Множитель цены (активный сценарий)", driver("price"), "drivers", "num"),
        Line("volume_mult", "Множитель объёма", driver("volume"), "drivers", "num"),
        Line("variable_mult", "Множитель переменных затрат", driver("variable_costs"), "drivers", "num"),
        Line("fixed_mult", "Множитель постоянных затрат", driver("fixed_costs"), "drivers", "num"),
    ]
    rev_parts, var_parts, fix_parts = [], [], []
    for i, s in enumerate(mi.revenue_streams):
        units = Series("volume_%d" % i) * Ref("volume_mult")
        if s.capacity is not None:
            units = Min(units, Input("capacity_%d" % i))
        lines.append(Line("units_%d" % i, "Объём: %s, %s" % (s.name, s.unit), units, "pl", "num"))
        lines.append(Line("revenue_%d" % i, "Выручка: %s" % s.name,
                          Ref("units_%d" % i) * Input("price_%d" % i) * Ref("price_mult"), "pl"))
        lines.append(Line("variable_%d" % i, "Переменные затраты: %s" % s.name,
                          Ref("units_%d" % i) * Input("variable_cost_%d" % i) * Ref("variable_mult"), "pl"))
        rev_parts.append(Ref("revenue_%d" % i))
        var_parts.append(Ref("variable_%d" % i))
    for j, c in enumerate(mi.fixed_costs):
        lines.append(Line("fixed_cost_%d" % j, "Постоянные: %s" % c.name,
                          Series("fixed_%d" % j) * Ref("fixed_mult"), "pl"))
        fix_parts.append(Ref("fixed_cost_%d" % j))

    lines += [
        Line("revenue", "Выручка", _add(rev_parts), "pl"),
        Line("variable_costs", "Переменные затраты", _add(var_parts), "pl"),
        Line("gross_profit", "Маржинальный доход", Ref("revenue") - Ref("variable_costs"), "pl"),
        Line("fixed_costs", "Постоянные затраты", _add(fix_parts), "pl"),
        Line("ebitda", "EBITDA", Ref("gross_profit") - Ref("fixed_costs"), "pl"),
        Line("depreciation", "Амортизация", Series("depreciation_plan"), "pl"),
        Line("ebit", "Операционная прибыль (EBIT)", Ref("ebitda") - Ref("depreciation"), "pl"),
        Line("interest", "Проценты по кредитам", Series("loan_interest"), "pl"),
        Line("ebt", "Прибыль до налога", Ref("ebit") - Ref("interest"), "pl"),
        Line("tax_loss_pool", "Перенесённый убыток на конец месяца",
             Max(0, Ref("tax_loss_pool", 1) - Ref("ebt")), "pl"),
        Line("taxable_income", "Налогооблагаемая прибыль",
             Max(0, Ref("ebt") - Ref("tax_loss_pool", 1)), "pl"),
        Line("tax", "КПН", Ref("taxable_income") * Input("cit_rate"), "pl"),
        Line("net_income", "Чистая прибыль", Ref("ebt") - Ref("tax"), "pl"),

        Line("cf_operating", "Операционный денежный поток",
             Ref("net_income") + Ref("depreciation")
             - (Ref("receivables") - Ref("receivables", 1))
             + (Ref("payables") - Ref("payables", 1)), "cf"),
        Line("capex", "Капвложения", Series("capex_spend"), "cf"),
        Line("cf_investing", "Инвестиционный денежный поток", -Ref("capex"), "cf"),
        Line("equity_in", "Взносы в капитал", Series("equity_in"), "cf"),
        Line("cf_financing", "Финансовый денежный поток",
             Ref("equity_in") + Series("loan_draw") - Series("loan_principal"), "cf"),
        Line("net_cash_flow", "Чистый денежный поток",
             Ref("cf_operating") + Ref("cf_investing") + Ref("cf_financing"), "cf"),

        Line("cash", "Деньги", Input("opening_cash") + Sum("net_cash_flow"), "bs"),
        Line("receivables", "Дебиторская задолженность",
             Ref("revenue") * Input("dso_days") / 30, "bs"),
        Line("fixed_assets_net", "Основные средства (остаточная стоимость)",
             Sum("capex") - Sum("depreciation"), "bs"),
        Line("total_assets", "Итого активы",
             Ref("cash") + Ref("receivables") + Ref("fixed_assets_net"), "bs"),
        Line("payables", "Кредиторская задолженность",
             (Ref("variable_costs") + Ref("fixed_costs")) * Input("dpo_days") / 30, "bs"),
        Line("debt", "Кредиты", Ref("debt", 1) + Series("loan_draw") - Series("loan_principal"), "bs"),
        Line("equity_paid", "Уставный и вложенный капитал",
             Input("opening_cash") + Sum("equity_in"), "bs"),
        Line("retained_earnings", "Нераспределённая прибыль", Sum("net_income"), "bs"),
        Line("total_liabilities_equity", "Итого обязательства и капитал",
             Ref("payables") + Ref("debt") + Ref("equity_paid") + Ref("retained_earnings"), "bs"),
        Line("balance_diff", "Проверка: активы − пассивы (должно быть 0)",
             Ref("total_assets") - Ref("total_liabilities_equity"), "check"),
    ]

    return Ctx(
        inputs=inputs,
        series=series,
        lines={ln.name: ln for ln in lines},
        periods=n,
        labels=labels,
        meta={"inputs": mi},
    )
