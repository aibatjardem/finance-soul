import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "plugins" / "finance-soul" / "kernel" / "run.py"
MODEL = ROOT / "examples" / "edtech" / ".finsoul" / "models" / "main"


def test_example_has_no_tbd():
    for f in ("company.md", "metrics.md", "assumptions.md"):
        assert "TBD" not in (MODEL.parents[1] / f).read_text(encoding="utf-8"), f


def test_example_up_to_date(tmp_path):
    r = subprocess.run([sys.executable, str(RUN), "build", str(MODEL / "inputs.json"), "--out", str(tmp_path),
                        "--no-xlsx"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    hint = "устарел: пересобери пример (см. CLAUDE.md)"
    fresh = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert fresh == (MODEL / "out" / "report.md").read_text(encoding="utf-8"), "report.md " + hint
    # Last float digits differ between Python versions (libm), so compare numbers with a tolerance.
    fresh_checks = json.loads((tmp_path / "checks.json").read_text(encoding="utf-8"))
    committed = json.loads((MODEL / "out" / "checks.json").read_text(encoding="utf-8"))
    assert _approx(fresh_checks) == committed, "checks.json " + hint


def _approx(v):
    if isinstance(v, dict):
        return {k: _approx(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_approx(x) for x in v]
    if isinstance(v, float):
        return pytest.approx(v, rel=1e-9, abs=1e-9)
    return v
