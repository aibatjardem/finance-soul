import pytest

from finsoul.graph import (
    Const, Ctx, Eq, Ge, Gt, If, Input, Line, Max, Min, Pick, Ref, Series, Sum, evaluate,
)


def make_ctx(lines, inputs=None, series=None, periods=3):
    return Ctx(
        inputs=inputs or {},
        series=series or {},
        lines={ln.name: ln for ln in lines},
        periods=periods,
    )


def ab_ctx():
    return make_ctx(
        [
            Line("a", "A", Series("v"), "pl"),
            Line("b", "B", Ref("a") * 2 + Ref("b", lag=1), "pl"),
        ],
        series={"v": [1, 2, 3]},
    )


def test_arithmetic_and_lag():
    values = evaluate(ab_ctx())
    assert values["a"] == [1, 2, 3]
    assert values["b"] == [2, 6, 12]


def test_to_excel_renders_addresses():
    ctx = ab_ctx()
    b = ctx.lines["b"].expr
    assert b.to_excel(ctx, 1) == "'Модель'!C2*2+'Модель'!B3"
    assert b.to_excel(ctx, 0) == "'Модель'!B2*2+0"


def test_series_and_input_addresses():
    ctx = make_ctx([Line("a", "A", Series("v") * Input("k"), "pl")],
                   inputs={"k": 3}, series={"v": [1, 2, 3]})
    assert evaluate(ctx)["a"] == [3, 6, 9]
    rendered = ctx.lines["a"].expr.to_excel(ctx, 0)
    assert rendered.startswith("'Входы'!")
    assert "$" in rendered.split("*")[1]  # scalar input is an absolute reference


def test_pick_and_if():
    ctx = make_ctx(
        [
            Line("a", "A", Series("v"), "pl"),
            Line("p", "P", Pick(Input("s"), [Const(1), Const(5)]), "pl"),
            Line("c", "C", If(Gt(Ref("a"), Const(1)), Const(10), Const(0)), "pl"),
            Line("d", "D", If(Ge(Ref("a"), Const(2)), Const(1), Const(0)), "pl"),
            Line("e", "E", If(Eq(Ref("a"), Const(3)), Const(1), Const(0)), "pl"),
        ],
        inputs={"s": 2},
        series={"v": [1, 2, 3]},
    )
    values = evaluate(ctx)
    assert values["p"] == [5, 5, 5]
    assert values["c"] == [0, 10, 10]
    assert values["d"] == [0, 1, 1]
    assert values["e"] == [0, 0, 1]
    assert ctx.lines["p"].expr.to_excel(ctx, 0).startswith("CHOOSE('Входы'!$C$")
    assert ctx.lines["c"].expr.to_excel(ctx, 0).startswith("IF(")


def test_max_min_and_negation():
    ctx = make_ctx(
        [
            Line("a", "A", Series("v"), "pl"),
            Line("m", "M", Max(Const(0), -Ref("a") + 2), "pl"),
            Line("n", "N", Min(Ref("a"), Const(2)) / 2, "pl"),
        ],
        series={"v": [1, 2, 3]},
    )
    values = evaluate(ctx)
    assert values["m"] == [1, 0, 0]
    assert values["n"] == [0.5, 1, 1]
    assert ctx.lines["m"].expr.to_excel(ctx, 0) == "MAX(0,-('Модель'!B2)+2)"


def test_cycle_detected():
    ctx = make_ctx([Line("a", "A", Ref("b"), "pl"), Line("b", "B", Ref("a"), "pl")])
    with pytest.raises(ValueError, match="цикл"):
        evaluate(ctx)


def test_cum_sum():
    ctx = make_ctx([Line("a", "A", Series("v"), "pl"), Line("s", "S", Sum("a"), "pl")],
                   series={"v": [1, 2, 3]})
    assert evaluate(ctx)["s"] == [1, 3, 6]
    assert ctx.lines["s"].expr.to_excel(ctx, 2) == "SUM('Модель'!B2:D2)"


def test_unknown_reference_is_clear_error():
    ctx = make_ctx([Line("a", "A", Ref("nope"), "pl")])
    with pytest.raises(KeyError, match="nope"):
        evaluate(ctx)
