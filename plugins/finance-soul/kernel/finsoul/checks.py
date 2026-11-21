"""Integrity checks. An error means the model must not be handed over."""
from typing import Dict, List

from .graph import Ctx

BALANCE_TOLERANCE = 0.5
RELATIVE_TOLERANCE = 1e-9


def _tol(scale: float) -> float:
    """Absolute 0.5 for normal models; relative for huge ones, where float rounding alone
    exceeds 0.5."""
    return max(BALANCE_TOLERANCE, RELATIVE_TOLERANCE * abs(scale))


def run_checks(ctx: Ctx, values: Dict[str, List[float]]) -> List[dict]:
    out: List[dict] = []
    for t, diff in enumerate(values["balance_diff"]):
        if abs(diff) > _tol(values["total_assets"][t]):
            out.append({
                "id": "balance_mismatch", "level": "error", "period": t,
                "message": "баланс не сходится в месяце %d: активы − пассивы = %.2f" % (t + 1, diff),
            })
            break
    opening = ctx.inputs.get("opening_cash", 0.0)
    cash, flow = values["cash"], values["net_cash_flow"]
    for t in range(ctx.periods):
        prev = opening if t == 0 else cash[t - 1]
        if abs(prev + flow[t] - cash[t]) > _tol(max(abs(prev), abs(cash[t]))):
            out.append({
                "id": "cash_mismatch", "level": "error", "period": t,
                "message": "деньги не сходятся с ДДС в месяце %d" % (t + 1),
            })
            break
    ni, re_ = values["net_income"], values["retained_earnings"]
    for t in range(ctx.periods):
        prev = 0.0 if t == 0 else re_[t - 1]
        if abs(prev + ni[t] - re_[t]) > _tol(max(abs(prev), abs(re_[t]))):
            out.append({
                "id": "retained_earnings_mismatch", "level": "error", "period": t,
                "message": "нераспределённая прибыль не сворачивается в месяце %d" % (t + 1),
            })
            break
    return out
