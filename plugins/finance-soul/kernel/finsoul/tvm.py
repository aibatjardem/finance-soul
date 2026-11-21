"""Time value of money. flows[0] happens now and is not discounted."""
from typing import List, Optional, Sequence


def npv(rate: float, flows: Sequence[float]) -> float:
    """Unlike Excel's NPV, flows[0] is at time 0. In Excel: =B + NPV(r, C:...)."""
    return sum(f / (1 + rate) ** i for i, f in enumerate(flows))


def _has_sign_change(flows: Sequence[float]) -> bool:
    return any(f < 0 for f in flows) and any(f > 0 for f in flows)


def irr(flows: Sequence[float]) -> Optional[float]:
    """Bisection on [-0.99, 10]. None if flows never change sign or no root
    in that range."""
    if len(flows) < 2 or not _has_sign_change(flows):
        return None
    # -0.99, not -0.9999: 0.0001**i underflows to 0.0 after ~80 periods.
    lo, hi = -0.99, 10.0
    try:
        f_lo, f_hi = npv(lo, flows), npv(hi, flows)
    except (ZeroDivisionError, OverflowError):
        return None
    if f_lo * f_hi > 0:
        return None
    for _ in range(300):
        mid = (lo + hi) / 2
        f_mid = npv(mid, flows)
        if abs(f_mid) < 1e-12 or hi - lo < 1e-12:
            return mid
        if f_lo * f_mid < 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid
    return (lo + hi) / 2


def _payback(flows: Sequence[float]) -> Optional[float]:
    cum = 0.0
    for i, f in enumerate(flows):
        prev = cum
        cum += f
        if i > 0 and prev < 0 <= cum:
            return (i - 1) + (-prev / f)
    return None


def payback_period(flows: Sequence[float]) -> Optional[float]:
    """Periods until the running total turns non-negative, interpolated."""
    return _payback(flows)


def discounted_payback(rate: float, flows: Sequence[float]) -> Optional[float]:
    return _payback([f / (1 + rate) ** i for i, f in enumerate(flows)])


def annuity_payment(rate_per_period: float, n: int, principal: float) -> float:
    if n <= 0:
        raise ValueError("срок кредита должен быть больше нуля")
    if rate_per_period == 0:
        return principal / n
    r = rate_per_period
    return principal * r / (1 - (1 + r) ** -n)


def monthly_rate(annual: float) -> float:
    """Nominal monthly rate (annual / 12), the way banks in Kazakhstan quote loans."""
    return annual / 12


def annuity_schedule(rate_per_period: float, n: int, principal: float) -> List[dict]:
    """Rows of {interest, principal, balance} after each payment."""
    pay = annuity_payment(rate_per_period, n, principal)
    balance = principal
    rows = []
    for _ in range(n):
        interest = balance * rate_per_period
        repaid = pay - interest
        balance -= repaid
        rows.append({"interest": interest, "principal": repaid, "balance": max(balance, 0.0)})
    return rows
