"""report.md: every number comes from the kernel's results, nothing is typed by hand."""
from typing import Dict, List, Optional

from .excel import month_labels
from .inputs import ModelInputs

UNDEFINED = "не определена"
SC_TITLES = [("base", "Базовый"), ("upside", "Оптимистичный"), ("downside", "Пессимистичный")]
DRIVER_TITLES = {"price": "Цена", "volume": "Объём", "variable_costs": "Переменные затраты",
                 "fixed_costs": "Постоянные затраты"}


def money(v: Optional[float], currency: str = "") -> str:
    if v is None:
        return UNDEFINED
    s = "{:,.0f}".format(v).replace(",", " ")
    return "%s %s" % (s, currency) if currency else s


def pct(v: Optional[float]) -> str:
    return UNDEFINED if v is None else ("%.1f%%" % (v * 100)).replace(".", ",")


def num(v: Optional[float], digits: int = 1) -> str:
    return UNDEFINED if v is None else ("%.*f" % (digits, v)).replace(".", ",")


def month(m: Optional[float], mi: ModelInputs) -> str:
    if m is None:
        return "не достигается за горизонт"
    idx = int(m) - 1
    labels = month_labels(mi.start, mi.months)
    return "%s-й месяц (%s)" % (num(m, 0) if float(m).is_integer() else num(m), labels[min(idx, len(labels) - 1)])


def _years(values: List[float], n: int) -> List[float]:
    return [sum(values[y * 12:(y + 1) * 12]) for y in range((n + 11) // 12)]


def render_report(mi: ModelInputs, scen: Dict[str, dict], sens: List[dict]) -> str:
    cur = mi.currency
    base = scen[mi.scenario]
    v, ue, cm = base["values"], base["unit_economics"], base["cash_metrics"]
    errors = [c for c in base["checks"] if c["level"] == "error"]
    warnings = [c for c in base["checks"] if c["level"] == "warning"]
    L: List[str] = []
    add = L.append

    add("# %s — финансовая модель" % mi.name)
    add("")
    add("Горизонт: %d мес. с %s · валюта: %s · сценарий отчёта: %s" % (
        mi.months, mi.start, cur, dict(SC_TITLES)[mi.scenario].lower()))
    add("")
    if errors:
        add("> **Модель не прошла проверки целостности — не передавать дальше.** См. раздел «Проверки».")
        add("")

    add("## Итог")
    add("")
    add("- Выручка за горизонт: **%s**" % money(sum(v["revenue"]), cur))
    add("- Безубыточность по EBITDA: **%s**" % month(cm["breakeven_month"], mi))
    add("- Пиковая потребность в деньгах до финансирования: **%s**" % money(cm["peak_funding_need"], cur))
    add("- NPV свободного денежного потока (ставка %s годовых): **%s**; IRR: **%s**" % (
        pct(cm["discount_rate_annual"]), money(cm["npv_fcf"], cur), pct(cm["irr_fcf"])))
    add("- LTV/CAC: **%s**" % num(ue["ltv_cac"]))
    add("")

    add("## Сценарии")
    add("")
    add("| Показатель | %s |" % " | ".join(t for _, t in SC_TITLES))
    add("|---|%s" % ("---:|" * len(SC_TITLES)))
    rows = [
        ("Выручка за горизонт", lambda r: money(sum(r["values"]["revenue"]), cur)),
        ("Чистая прибыль за горизонт", lambda r: money(sum(r["values"]["net_income"]), cur)),
        ("Минимум денег на счёте", lambda r: money(r["cash_metrics"]["min_cash"], cur)),
        ("Пиковая потребность в деньгах", lambda r: money(r["cash_metrics"]["peak_funding_need"], cur)),
        ("Безубыточность по EBITDA, месяц", lambda r: num(r["cash_metrics"]["breakeven_month"], 0)
         if r["cash_metrics"]["breakeven_month"] else "нет"),
        ("NPV FCF", lambda r: money(r["cash_metrics"]["npv_fcf"], cur)),
        ("IRR FCF", lambda r: pct(r["cash_metrics"]["irr_fcf"])),
    ]
    for title, fn in rows:
        add("| %s | %s |" % (title, " | ".join(fn(scen[k]) for k, _ in SC_TITLES)))
    add("")
    add("Множители сценариев (цена / объём / перем. затраты / пост. затраты): " + "; ".join(
        "%s %s/%s/%s/%s" % (t.lower(), *(num(getattr(mi.scenarios[k], d), 2) for d in
                                          ("price", "volume", "variable_costs", "fixed_costs")))
        for k, t in SC_TITLES))
    add("")

    add("## Чувствительность NPV")
    add("")
    add("Каждый драйвер базового сценария сдвинут на ±10%, остальное без изменений. Сверху — самый сильный.")
    add("")
    add("| Драйвер | −10% | +10% | Размах |")
    add("|---|---:|---:|---:|")
    for r in sens:
        add("| %s | %s | %s | %s |" % (DRIVER_TITLES[r["driver"]], money(r["low"], cur),
                                       money(r["high"], cur), money(abs(r["high"] - r["low"]), cur)))
    add("")

    add("## Юнит-экономика")
    add("")
    add("Единица: %s." % ue["unit"])
    add("")
    add("| Показатель | Значение |")
    add("|---|---:|")
    add("| Цена | %s |" % money(ue["price"], cur))
    add("| Маржинальный доход на единицу | %s |" % money(ue["contribution_per_unit"], cur))
    add("| Маржинальность | %s |" % pct(ue["contribution_margin"]))
    add("| Точка безубыточности, единиц в месяц | %s |" % num(ue["breakeven_units_per_month"], 0))
    add("| CAC | %s |" % money(ue["cac"], cur))
    add("| Отток в месяц | %s |" % pct(ue["churn_monthly"]))
    add("| LTV (маржинальный доход / отток) | %s |" % money(ue["ltv"], cur))
    add("| LTV/CAC | %s |" % num(ue["ltv_cac"]))
    add("| Окупаемость CAC, мес. | %s |" % num(ue["cac_payback_months"]))
    add("")

    add("## Деньги")
    add("")
    add("- Минимум денег на счёте: %s, %s" % (money(cm["min_cash"], cur), month(cm["min_cash_month"], mi)))
    if cm["first_negative_cash_month"] is not None:
        add("- **Деньги уходят в минус: %s.** Runway — %d полных мес." % (
            month(cm["first_negative_cash_month"], mi), cm["runway_months"]))
    else:
        add("- С заложенным финансированием деньги не уходят в минус за горизонт.")
    add("- Окупаемость свободного денежного потока: %s" % month(cm["payback_month"], mi))
    add("")

    add("## P&L по годам")
    add("")
    years = (mi.months + 11) // 12
    add("| Статья | %s |" % " | ".join("Год %d" % (y + 1) for y in range(years)))
    add("|---|%s" % ("---:|" * years))
    for key, title in (("revenue", "Выручка"), ("gross_profit", "Маржинальный доход"),
                       ("fixed_costs", "Постоянные затраты"), ("ebitda", "EBITDA"),
                       ("depreciation", "Амортизация"), ("interest", "Проценты"),
                       ("tax", "КПН"), ("net_income", "Чистая прибыль")):
        add("| %s | %s |" % (title, " | ".join(money(x) for x in _years(v[key], mi.months))))
    add("")
    add("Деньги на конец года: %s" % ", ".join(
        money(v["cash"][min((y + 1) * 12, mi.months) - 1], cur) for y in range(years)))
    add("")

    add("## Проверки")
    add("")
    if not errors:
        add("- Баланс сходится в каждом месяце, деньги сходятся с ДДС, нераспределённая прибыль сворачивается.")
    for c in errors:
        add("- **Ошибка:** %s" % c["message"])
    for c in warnings:
        add("- Предупреждение: %s" % c["message"])
    add("")

    add("## Допущения и упрощения v0.1")
    add("")
    add("- НДС сквозной: выручка и затраты указаны без НДС, НДС не проходит через баланс.")
    add("- КПН %s начисляется и платится в том же месяце; убытки переносятся вперёд. Источник ставки: %s." % (
        pct(mi.tax.cit_rate), mi.tax.source or "не указан"))
    add("- Одна валюта модели (%s), без курсовых разниц." % cur)
    add("- Деньги на начало считаются вложенным капиталом; кредиты — аннуитет с месяца после получения.")
    add("- Дебиторка = выручка × дни/30, кредиторка = затраты × дни/30.")
    if mi.assumptions_ref:
        add("- Источники допущений: %s." % mi.assumptions_ref)
    add("")
    add("_Черновик для проверки человеком. Не является финансовой, налоговой или юридической консультацией: "
        "структуру, налоги и зарплатные начисления должен проверить бухгалтер._")
    add("")
    return "\n".join(L)
