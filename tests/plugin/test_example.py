import subprocess
import sys
from pathlib import Path

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
    for name in ("report.md", "checks.json"):
        fresh = (tmp_path / name).read_text(encoding="utf-8")
        committed = (MODEL / "out" / name).read_text(encoding="utf-8")
        assert fresh == committed, "%s устарел: пересобери пример (см. CLAUDE.md)" % name
