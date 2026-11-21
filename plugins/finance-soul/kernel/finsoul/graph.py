"""Model as named line expressions over inputs and periods.

One expression is both evaluated in Python (``eval``) and rendered as an Excel
formula (``to_excel``). That is the whole trick that keeps the report and the
workbook in agreement: they are produced from the same description.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple, Union

Number = Union[int, float]

MODEL_SHEET = "Модель"
INPUT_SHEET = "Входы"


def col_letter(index: int) -> str:
    """1 -> A, 2 -> B, 27 -> AA."""
    letters = ""
    while index > 0:
        index, rem = divmod(index - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def _fmt_number(v: float) -> str:
    if float(v).is_integer():
        return str(int(v))
    return repr(float(v))


class Expr:
    prec = 9  # atoms bind tightest

    def eval(self, ctx: "Ctx", t: int) -> float:
        raise NotImplementedError

    def to_excel(self, ctx: "Ctx", t: int) -> str:
        raise NotImplementedError

    def __add__(self, other): return BinOp("+", self, wrap(other))
    def __radd__(self, other): return BinOp("+", wrap(other), self)
    def __sub__(self, other): return BinOp("-", self, wrap(other))
    def __rsub__(self, other): return BinOp("-", wrap(other), self)
    def __mul__(self, other): return BinOp("*", self, wrap(other))
    def __rmul__(self, other): return BinOp("*", wrap(other), self)
    def __truediv__(self, other): return BinOp("/", self, wrap(other))
    def __rtruediv__(self, other): return BinOp("/", wrap(other), self)
    def __neg__(self): return Neg(self)


def wrap(v: Union[Expr, Number]) -> Expr:
    if isinstance(v, Expr):
        return v
    if isinstance(v, (int, float)):
        return Const(v)
    raise TypeError("ожидалось выражение или число, получено %r" % (v,))


class Const(Expr):
    def __init__(self, v: Number):
        self.v = float(v)

    def eval(self, ctx, t):
        return self.v

    def to_excel(self, ctx, t):
        return _fmt_number(self.v)


class Input(Expr):
    """A scalar on the inputs sheet."""

    def __init__(self, name: str):
        self.name = name

    def eval(self, ctx, t):
        if self.name not in ctx.inputs:
            raise KeyError("нет входа %r" % self.name)
        return float(ctx.inputs[self.name])

    def to_excel(self, ctx, t):
        return ctx.layout.input_addr(self.name)


class Series(Expr):
    """A per-period input row on the inputs sheet."""

    def __init__(self, name: str):
        self.name = name

    def eval(self, ctx, t):
        if self.name not in ctx.series:
            raise KeyError("нет входного ряда %r" % self.name)
        return float(ctx.series[self.name][t])

    def to_excel(self, ctx, t):
        return ctx.layout.series_addr(self.name, t)


class Ref(Expr):
    """Another model line, optionally lagged. Before period 0 it is zero."""

    def __init__(self, name: str, lag: int = 0):
        self.name = name
        self.lag = lag

    def eval(self, ctx, t):
        if t - self.lag < 0:
            return 0.0
        return ctx.value(self.name, t - self.lag)

    def to_excel(self, ctx, t):
        if t - self.lag < 0:
            return "0"
        ctx.line(self.name)
        return ctx.layout.line_addr(self.name, t - self.lag)


class Sum(Expr):
    """Running total of a line over periods 0..t."""

    def __init__(self, name: str):
        self.name = name

    def eval(self, ctx, t):
        return sum(ctx.value(self.name, i) for i in range(t + 1))

    def to_excel(self, ctx, t):
        ctx.line(self.name)
        return "SUM(%s:%s)" % (
            ctx.layout.line_addr(self.name, 0, qualified=True),
            ctx.layout.line_addr(self.name, t, qualified=False),
        )


class BinOp(Expr):
    _prec = {"+": 1, "-": 1, "*": 2, "/": 2}

    def __init__(self, op: str, left: Expr, right: Expr):
        self.op, self.left, self.right = op, left, right
        self.prec = self._prec[op]

    def eval(self, ctx, t):
        a = self.left.eval(ctx, t)
        b = self.right.eval(ctx, t)
        if self.op == "+":
            return a + b
        if self.op == "-":
            return a - b
        if self.op == "*":
            return a * b
        if b == 0:
            raise ZeroDivisionError("деление на ноль в периоде %d" % t)
        return a / b

    def to_excel(self, ctx, t):
        left = self.left.to_excel(ctx, t)
        right = self.right.to_excel(ctx, t)
        if self.left.prec < self.prec:
            left = "(%s)" % left
        # a-(b+c), a/(b*c): the right side needs parens at equal precedence too.
        if self.right.prec < self.prec or (
            self.right.prec == self.prec and self.op in "-/"
        ):
            right = "(%s)" % right
        return "%s%s%s" % (left, self.op, right)


class Neg(Expr):
    def __init__(self, inner: Expr):
        self.inner = inner

    def eval(self, ctx, t):
        return -self.inner.eval(ctx, t)

    def to_excel(self, ctx, t):
        return "-(%s)" % self.inner.to_excel(ctx, t)


class _Func(Expr):
    fn = ""

    def __init__(self, *args: Union[Expr, Number]):
        self.args = [wrap(a) for a in args]

    def to_excel(self, ctx, t):
        return "%s(%s)" % (self.fn, ",".join(a.to_excel(ctx, t) for a in self.args))


class Max(_Func):
    fn = "MAX"

    def eval(self, ctx, t):
        return max(a.eval(ctx, t) for a in self.args)


class Min(_Func):
    fn = "MIN"

    def eval(self, ctx, t):
        return min(a.eval(ctx, t) for a in self.args)


class _Cmp(Expr):
    sym = ""
    prec = 0

    def __init__(self, a: Union[Expr, Number], b: Union[Expr, Number]):
        self.a, self.b = wrap(a), wrap(b)

    def to_excel(self, ctx, t):
        return "%s%s%s" % (self.a.to_excel(ctx, t), self.sym, self.b.to_excel(ctx, t))


class Gt(_Cmp):
    sym = ">"

    def eval(self, ctx, t):
        return 1.0 if self.a.eval(ctx, t) > self.b.eval(ctx, t) else 0.0


class Ge(_Cmp):
    sym = ">="

    def eval(self, ctx, t):
        return 1.0 if self.a.eval(ctx, t) >= self.b.eval(ctx, t) else 0.0


class Eq(_Cmp):
    sym = "="

    def eval(self, ctx, t):
        return 1.0 if self.a.eval(ctx, t) == self.b.eval(ctx, t) else 0.0


class If(Expr):
    def __init__(self, cond: _Cmp, a: Union[Expr, Number], b: Union[Expr, Number]):
        self.cond, self.a, self.b = cond, wrap(a), wrap(b)

    def eval(self, ctx, t):
        return self.a.eval(ctx, t) if self.cond.eval(ctx, t) else self.b.eval(ctx, t)

    def to_excel(self, ctx, t):
        return "IF(%s,%s,%s)" % (
            self.cond.to_excel(ctx, t), self.a.to_excel(ctx, t), self.b.to_excel(ctx, t),
        )


class Pick(Expr):
    """CHOOSE(selector, options...): the live scenario switch."""

    def __init__(self, selector: Expr, options: Sequence[Union[Expr, Number]]):
        self.selector = selector
        self.options = [wrap(o) for o in options]

    def eval(self, ctx, t):
        i = int(round(self.selector.eval(ctx, t)))
        if not 1 <= i <= len(self.options):
            raise ValueError("переключатель вне диапазона 1..%d: %d" % (len(self.options), i))
        return self.options[i - 1].eval(ctx, t)

    def to_excel(self, ctx, t):
        return "CHOOSE(%s,%s)" % (
            self.selector.to_excel(ctx, t),
            ",".join(o.to_excel(ctx, t) for o in self.options),
        )


@dataclass
class Line:
    name: str
    label: str
    expr: Expr
    section: str
    fmt: str = "money"


class Layout:
    """Where every input, series and line lives in the workbook."""

    def __init__(self, input_rows: Dict[str, int], series_rows: Dict[str, int],
                 line_rows: Dict[str, int], series_first_col: int = 3,
                 line_first_col: int = 2):
        self.input_rows = input_rows
        self.series_rows = series_rows
        self.line_rows = line_rows
        self.series_first_col = series_first_col
        self.line_first_col = line_first_col

    @classmethod
    def default(cls, ctx: "Ctx") -> "Layout":
        input_rows = {name: i + 2 for i, name in enumerate(ctx.inputs)}
        first_series = len(ctx.inputs) + 4
        series_rows = {name: first_series + i for i, name in enumerate(ctx.series)}
        line_rows = {name: i + 2 for i, name in enumerate(ctx.lines)}
        return cls(input_rows, series_rows, line_rows)

    def input_addr(self, name: str) -> str:
        if name not in self.input_rows:
            raise KeyError("нет входа %r" % name)
        return "'%s'!$C$%d" % (INPUT_SHEET, self.input_rows[name])

    def series_addr(self, name: str, t: int) -> str:
        if name not in self.series_rows:
            raise KeyError("нет входного ряда %r" % name)
        return "'%s'!%s%d" % (INPUT_SHEET, col_letter(self.series_first_col + t),
                              self.series_rows[name])

    def line_cell(self, name: str, t: int) -> Tuple[int, int]:
        """(row, column) of a model line in period t."""
        return self.line_rows[name], self.line_first_col + t

    def line_addr(self, name: str, t: int, qualified: bool = True) -> str:
        row, col = self.line_cell(name, t)
        cell = "%s%d" % (col_letter(col), row)
        return "'%s'!%s" % (MODEL_SHEET, cell) if qualified else cell


@dataclass
class Ctx:
    inputs: Dict[str, float]
    series: Dict[str, List[float]]
    lines: Dict[str, Line]
    periods: int
    layout: Optional[Layout] = None
    _cache: Dict[Tuple[str, int], float] = field(default_factory=dict, repr=False)
    _stack: Set[Tuple[str, int]] = field(default_factory=set, repr=False)
    _path: List[str] = field(default_factory=list, repr=False)

    def __post_init__(self):
        if self.layout is None:
            self.layout = Layout.default(self)

    def line(self, name: str) -> Line:
        if name not in self.lines:
            raise KeyError("нет строки модели %r" % name)
        return self.lines[name]

    def value(self, name: str, t: int) -> float:
        key = (name, t)
        if key in self._cache:
            return self._cache[key]
        line = self.line(name)
        if key in self._stack:
            raise ValueError("цикл: %s -> %s" % (" -> ".join(self._path), name))
        self._stack.add(key)
        self._path.append(name)
        try:
            v = line.expr.eval(self, t)
        finally:
            self._stack.discard(key)
            self._path.pop()
        self._cache[key] = v
        return v

    def reset(self) -> None:
        self._cache.clear()


def evaluate(ctx: Ctx) -> Dict[str, List[float]]:
    """Values of every line in every period. Periods go in order, so lagged
    chains never recurse deeper than one period."""
    ctx.reset()
    for t in range(ctx.periods):
        for name in ctx.lines:
            ctx.value(name, t)
    return {name: [ctx._cache[(name, t)] for t in range(ctx.periods)] for name in ctx.lines}
