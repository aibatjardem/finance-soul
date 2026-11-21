"""finance-soul kernel CLI.

Exit codes: 0 ok · 1 integrity errors (files are still written) · 2 bad inputs.
"""
import argparse
import json
import os
import sys
from typing import List, Optional

from . import __version__
from .inputs import InputError, load_inputs
from .report import render_report
from .scenarios import run_scenarios, sensitivity


def _summary(res: dict) -> dict:
    cm = dict(res["cash_metrics"])
    cm.pop("fcf", None)
    ue = dict(res["unit_economics"])
    return {"cash_metrics": cm, "unit_economics": ue}


def cmd_build(args) -> int:
    try:
        mi = load_inputs(args.inputs)
    except InputError as e:
        for err in e.all:
            print("%s: %s" % (err.path, err.message), file=sys.stderr)
        return 2

    scen = run_scenarios(mi)
    sens = sensitivity(mi)
    active = scen[mi.scenario]
    os.makedirs(args.out, exist_ok=True)

    with open(os.path.join(args.out, "report.md"), "w", encoding="utf-8") as fh:
        fh.write(render_report(mi, scen, sens))

    checks = active["checks"]
    payload = {
        "model": mi.name,
        "kernel_version": __version__,
        "scenario": mi.scenario,
        "errors": [c for c in checks if c["level"] == "error"],
        "warnings": [c for c in checks if c["level"] == "warning"],
        "scenario_results": {k: _summary(r) for k, r in scen.items()},
        "sensitivity": sens,
    }
    with open(os.path.join(args.out, "checks.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    if not args.no_xlsx:
        from .excel import write_xlsx
        try:
            write_xlsx(active["ctx"], os.path.join(args.out, "model.xlsx"), checks)
        except RuntimeError as e:
            print(str(e), file=sys.stderr)
            return 1

    print("Готово: %s (report.md, checks.json%s)" % (args.out, "" if args.no_xlsx else ", model.xlsx"))
    if payload["errors"]:
        for c in payload["errors"]:
            print("ОШИБКА: %s" % c["message"], file=sys.stderr)
        return 1
    for c in payload["warnings"]:
        print("Предупреждение: %s" % c["message"])
    return 0


def cmd_check_env(_args) -> int:
    print("Python %s" % sys.version.split()[0])
    try:
        import openpyxl
        print("openpyxl %s" % openpyxl.__version__)
        return 0
    except ImportError:
        print("openpyxl не установлен: python3 -m pip install --user openpyxl")
        return 1


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="finsoul", description="Finance Soul kernel %s" % __version__)
    sub = p.add_subparsers(dest="cmd")
    b = sub.add_parser("build", help="построить модель: report.md, checks.json, model.xlsx")
    b.add_argument("inputs")
    b.add_argument("--out", required=True)
    b.add_argument("--no-xlsx", action="store_true")
    b.set_defaults(fn=cmd_build)
    e = sub.add_parser("check-env", help="проверить Python и openpyxl")
    e.set_defaults(fn=cmd_check_env)
    args = p.parse_args(argv)
    if not getattr(args, "fn", None):
        p.print_help()
        return 2
    return args.fn(args)
