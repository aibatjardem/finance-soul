"""Base / upside / downside runs and one-at-a-time sensitivity (tornado)."""
import copy
from typing import Dict, List

from .checks import run_checks
from .graph import evaluate
from .inputs import DRIVERS, SCENARIO_NAMES, ModelInputs
from .metrics import cash_metrics, metric_checks, unit_economics
from .statements import build_model


def run_one(mi: ModelInputs) -> dict:
    ctx = build_model(mi)
    values = evaluate(ctx)
    ue = unit_economics(mi, values)
    cm = cash_metrics(mi, values)
    return {
        "ctx": ctx,
        "values": values,
        "unit_economics": ue,
        "cash_metrics": cm,
        "checks": run_checks(ctx, values) + metric_checks(ue, cm),
    }


def run_scenarios(mi: ModelInputs) -> Dict[str, dict]:
    out = {}
    for name in SCENARIO_NAMES:
        variant = copy.deepcopy(mi)
        variant.scenario = name
        out[name] = run_one(variant)
    return out


def sensitivity(mi: ModelInputs, metric: str = "npv_fcf", step: float = 0.1) -> List[dict]:
    """Each driver of the base scenario moved by ±step, everything else fixed."""
    rows = []
    for drv in DRIVERS:
        result = {"driver": drv}
        for side, factor in (("low", 1 - step), ("high", 1 + step)):
            variant = copy.deepcopy(mi)
            variant.scenario = "base"
            base = variant.scenarios["base"]
            setattr(base, drv, getattr(base, drv) * factor)
            result[side] = run_one(variant)["cash_metrics"][metric]
        rows.append(result)
    rows.sort(key=lambda r: abs(r["high"] - r["low"]), reverse=True)
    return rows
