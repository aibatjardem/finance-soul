"""inputs.json: schema, defaults and validation with readable Russian errors.

Months in inputs are 1-based (1 = first model month); the kernel uses t = month - 1.
"""
import difflib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

SCENARIO_NAMES = ("base", "upside", "downside")
DRIVERS = ("price", "volume", "variable_costs", "fixed_costs")
DEFAULT_SCENARIOS = {
    "base": {"price": 1.0, "volume": 1.0, "variable_costs": 1.0, "fixed_costs": 1.0},
    "upside": {"price": 1.0, "volume": 1.2, "variable_costs": 1.0, "fixed_costs": 1.0},
    "downside": {"price": 0.9, "volume": 0.8, "variable_costs": 1.15, "fixed_costs": 1.1},
}


class InputError(Exception):
    def __init__(self, path: str, message: str, all_errors: Optional[List["InputError"]] = None):
        super().__init__("%s: %s" % (path, message))
        self.path = path
        self.message = message
        self.all = all_errors if all_errors is not None else [self]


@dataclass
class Scenario:
    price: float = 1.0
    volume: float = 1.0
    variable_costs: float = 1.0
    fixed_costs: float = 1.0


@dataclass
class RevenueStream:
    name: str
    unit: str
    price: float
    variable_cost: float
    ramp: List[float]
    growth_monthly: float = 0.0
    capacity: Optional[float] = None


@dataclass
class FixedCost:
    name: str
    monthly: float
    growth_annual: float = 0.0
    start_month: int = 1


@dataclass
class Capex:
    name: str
    month: int
    amount: float
    life_months: int


@dataclass
class Equity:
    month: int
    amount: float


@dataclass
class Loan:
    name: str
    month: int
    amount: float
    rate_annual: float
    term_months: int


@dataclass
class Financing:
    equity: List[Equity] = field(default_factory=list)
    loans: List[Loan] = field(default_factory=list)


@dataclass
class WorkingCapital:
    dso_days: float = 0.0
    dpo_days: float = 0.0


@dataclass
class Tax:
    cit_rate: float = 0.2
    source: str = ""


@dataclass
class UnitEconomicsInputs:
    cac: Optional[float] = None
    churn_monthly: Optional[float] = None
    marketing_line: Optional[str] = None


@dataclass
class ModelInputs:
    name: str
    start: str
    months: int
    revenue_streams: List[RevenueStream]
    currency: str = "KZT"
    opening_cash: float = 0.0
    scenario: str = "base"
    scenarios: Dict[str, Scenario] = field(default_factory=dict)
    fixed_costs: List[FixedCost] = field(default_factory=list)
    capex: List[Capex] = field(default_factory=list)
    financing: Financing = field(default_factory=Financing)
    working_capital: WorkingCapital = field(default_factory=WorkingCapital)
    tax: Tax = field(default_factory=Tax)
    unit_economics: UnitEconomicsInputs = field(default_factory=UnitEconomicsInputs)
    discount_rate_annual: float = 0.25
    assumptions_ref: Optional[str] = None
    fx: Optional[dict] = None

    @property
    def scenario_index(self) -> int:
        return SCENARIO_NAMES.index(self.scenario) + 1


_MISSING = object()


class _Reader:
    """Reads fields, records every problem instead of stopping at the first."""

    def __init__(self, months: Optional[int] = None):
        self.errors: List[InputError] = []
        self.months = months

    def err(self, path: str, message: str) -> None:
        self.errors.append(InputError(path, message))

    def obj(self, d: Any, path: str, known: List[str]) -> Dict[str, Any]:
        if not isinstance(d, dict):
            self.err(path or "(корень)", "ожидался объект { ... }")
            return {}
        for key in d:
            if key not in known:
                hint = difflib.get_close_matches(key, known, n=1)
                tail = ", возможно, %s" % hint[0] if hint else ", допустимые: %s" % ", ".join(known)
                self.err(_join(path, key), "неизвестное поле%s" % tail)
        return d

    def num(self, d: Dict[str, Any], key: str, path: str, default: Any = _MISSING,
            minimum: Optional[float] = None, maximum: Optional[float] = None,
            integer: bool = False, nullable: bool = False) -> Any:
        p = _join(path, key)
        if key not in d or (d[key] is None and not nullable):
            if default is _MISSING:
                self.err(p, "обязательное %s" % ("целое число" if integer else "число"))
                return 0
            return default
        v = d[key]
        if v is None:
            return None
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            self.err(p, "ожидалось %s, получено %r" % ("целое число" if integer else "число", v))
            return 0
        if integer and not float(v).is_integer():
            self.err(p, "ожидалось целое число, получено %r" % v)
            return 0
        if minimum is not None and v < minimum:
            self.err(p, "не меньше %s, получено %s" % (minimum, v))
        if maximum is not None and v > maximum:
            self.err(p, "не больше %s, получено %s" % (maximum, v))
        return int(v) if integer else float(v)

    def month(self, d: Dict[str, Any], key: str, path: str, default: Any = _MISSING) -> int:
        v = self.num(d, key, path, default=default, minimum=1, integer=True)
        if self.months and isinstance(v, int) and v > self.months:
            self.err(_join(path, key), "месяц %d за горизонтом модели (%d мес.)" % (v, self.months))
        return v

    def text(self, d: Dict[str, Any], key: str, path: str, default: Any = _MISSING) -> Any:
        p = _join(path, key)
        if key not in d:
            if default is _MISSING:
                self.err(p, "обязательная строка")
                return ""
            return default
        v = d[key]
        if not isinstance(v, str) or not v.strip():
            self.err(p, "ожидалась непустая строка, получено %r" % (v,))
            return ""
        return v

    def items(self, d: Dict[str, Any], key: str, path: str, required: bool = False) -> List[Any]:
        p = _join(path, key)
        if key not in d:
            if required:
                self.err(p, "обязательный список")
            return []
        v = d[key]
        if not isinstance(v, list):
            self.err(p, "ожидался список [ ... ]")
            return []
        if required and not v:
            self.err(p, "список не может быть пустым")
        return v


def _join(path: str, key: str) -> str:
    return "%s.%s" % (path, key) if path else key


TOP_KEYS = [
    "name", "currency", "start", "months", "opening_cash", "scenario", "scenarios",
    "revenue_streams", "fixed_costs", "capex", "financing", "working_capital", "tax",
    "unit_economics", "discount_rate_annual", "assumptions_ref", "fx",
]


def parse_inputs(raw: Any) -> ModelInputs:
    r = _Reader()
    d = r.obj(raw, "", TOP_KEYS)
    months = r.num(d, "months", "", minimum=1, maximum=120, integer=True)
    r.months = months if isinstance(months, int) and 1 <= months <= 120 else None

    start = r.text(d, "start", "")
    if start and not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", start):
        r.err("start", "ожидался месяц в формате ГГГГ-ММ, получено %r" % start)

    scenarios: Dict[str, Scenario] = {}
    raw_sc = r.obj(d.get("scenarios", {}), "scenarios", list(SCENARIO_NAMES))
    for name in SCENARIO_NAMES:
        base = DEFAULT_SCENARIOS[name]
        sd = r.obj(raw_sc.get(name, {}), "scenarios.%s" % name, list(DRIVERS))
        scenarios[name] = Scenario(**{
            k: r.num(sd, k, "scenarios.%s" % name, default=base[k], minimum=0) for k in DRIVERS
        })

    scenario = d.get("scenario", "base")
    if scenario not in SCENARIO_NAMES:
        r.err("scenario", "неизвестный сценарий %r, допустимые: %s" % (scenario, ", ".join(SCENARIO_NAMES)))
        scenario = "base"

    streams = []
    for i, s in enumerate(r.items(d, "revenue_streams", "", required=True)):
        p = "revenue_streams[%d]" % i
        s = r.obj(s, p, ["name", "unit", "price", "variable_cost", "ramp", "growth_monthly", "capacity"])
        ramp_raw = r.items(s, "ramp", p, required=True)
        ramp = [r.num({"ramp[%d]" % j: v}, "ramp[%d]" % j, p, minimum=0)
                for j, v in enumerate(ramp_raw)]
        streams.append(RevenueStream(
            name=r.text(s, "name", p),
            unit=r.text(s, "unit", p, default="единица"),
            price=r.num(s, "price", p, minimum=0),
            variable_cost=r.num(s, "variable_cost", p, default=0.0, minimum=0),
            ramp=ramp,
            growth_monthly=r.num(s, "growth_monthly", p, default=0.0, minimum=-1, maximum=1),
            capacity=r.num(s, "capacity", p, default=None, minimum=0, nullable=True),
        ))

    fixed = []
    for i, f in enumerate(r.items(d, "fixed_costs", "")):
        p = "fixed_costs[%d]" % i
        f = r.obj(f, p, ["name", "monthly", "growth_annual", "start_month"])
        fixed.append(FixedCost(
            name=r.text(f, "name", p),
            monthly=r.num(f, "monthly", p, minimum=0),
            growth_annual=r.num(f, "growth_annual", p, default=0.0, minimum=-1),
            start_month=r.month(f, "start_month", p, default=1),
        ))

    capex = []
    for i, c in enumerate(r.items(d, "capex", "")):
        p = "capex[%d]" % i
        c = r.obj(c, p, ["name", "month", "amount", "life_months"])
        capex.append(Capex(
            name=r.text(c, "name", p),
            month=r.month(c, "month", p),
            amount=r.num(c, "amount", p, minimum=0),
            life_months=r.num(c, "life_months", p, minimum=1, integer=True),
        ))

    fd = r.obj(d.get("financing", {}), "financing", ["equity", "loans"])
    equity = []
    for i, e in enumerate(r.items(fd, "equity", "financing")):
        p = "financing.equity[%d]" % i
        e = r.obj(e, p, ["month", "amount"])
        equity.append(Equity(month=r.month(e, "month", p), amount=r.num(e, "amount", p, minimum=0)))
    loans = []
    for i, ln in enumerate(r.items(fd, "loans", "financing")):
        p = "financing.loans[%d]" % i
        ln = r.obj(ln, p, ["name", "month", "amount", "rate_annual", "term_months"])
        loans.append(Loan(
            name=r.text(ln, "name", p, default="кредит %d" % (i + 1)),
            month=r.month(ln, "month", p),
            amount=r.num(ln, "amount", p, minimum=0),
            rate_annual=r.num(ln, "rate_annual", p, minimum=0, maximum=5),
            term_months=r.num(ln, "term_months", p, minimum=1, maximum=600, integer=True),
        ))

    wd = r.obj(d.get("working_capital", {}), "working_capital", ["dso_days", "dpo_days"])
    wc = WorkingCapital(
        dso_days=r.num(wd, "dso_days", "working_capital", default=0.0, minimum=0, maximum=365),
        dpo_days=r.num(wd, "dpo_days", "working_capital", default=0.0, minimum=0, maximum=365),
    )

    td = r.obj(d.get("tax", {}), "tax", ["cit_rate", "source"])
    cit = r.num(td, "cit_rate", "tax", default=0.2, minimum=0, maximum=1)
    source = td.get("source", "")
    if cit and (not isinstance(source, str) or not source.strip()):
        r.err("tax.source", "укажи источник ставки КПН (статья кодекса, дата проверки)")
        source = ""

    ud = r.obj(d.get("unit_economics", {}), "unit_economics", ["cac", "churn_monthly", "marketing_line"])
    ue = UnitEconomicsInputs(
        cac=r.num(ud, "cac", "unit_economics", default=None, minimum=0, nullable=True),
        churn_monthly=r.num(ud, "churn_monthly", "unit_economics", default=None, minimum=0, maximum=1, nullable=True),
        marketing_line=ud.get("marketing_line"),
    )
    if ue.marketing_line is not None and ue.marketing_line not in [f.name for f in fixed]:
        r.err("unit_economics.marketing_line", "нет постоянной статьи %r в fixed_costs" % ue.marketing_line)

    mi = ModelInputs(
        name=r.text(d, "name", ""),
        start=start,
        months=months if isinstance(months, int) else 0,
        revenue_streams=streams,
        currency=r.text(d, "currency", "", default="KZT"),
        opening_cash=r.num(d, "opening_cash", "", default=0.0),
        scenario=scenario,
        scenarios=scenarios,
        fixed_costs=fixed,
        capex=capex,
        financing=Financing(equity=equity, loans=loans),
        working_capital=wc,
        tax=Tax(cit_rate=cit, source=source if isinstance(source, str) else ""),
        unit_economics=ue,
        discount_rate_annual=r.num(d, "discount_rate_annual", "", default=0.25, minimum=0, maximum=5),
        assumptions_ref=d.get("assumptions_ref"),
        fx=d.get("fx"),
    )
    if r.errors:
        first = r.errors[0]
        raise InputError(first.path, first.message, r.errors)
    return mi


def load_inputs(path: str) -> ModelInputs:
    try:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
    except FileNotFoundError:
        raise InputError(path, "файл не найден")
    except IsADirectoryError:
        raise InputError(path, "это папка, а нужен файл inputs.json")
    except UnicodeDecodeError:
        raise InputError(path, "файл не в кодировке UTF-8 — пересохрани его в UTF-8")
    except OSError as e:
        raise InputError(path, "не удалось прочитать файл: %s" % e.strerror)
    except json.JSONDecodeError as e:
        raise InputError(path, "некорректный JSON: строка %d, колонка %d: %s" % (e.lineno, e.colno, e.msg))
    return parse_inputs(raw)
