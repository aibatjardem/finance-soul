import json
import subprocess
import sys
from pathlib import Path

from finsoul.inputs import parse_inputs

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins" / "finance-soul"
PROFILES = sorted(p for p in (PLUGIN / "profiles").iterdir() if p.is_dir() and not p.name.startswith("._"))
SKILLS = ["setup", "soul", "kernel-reference", "assumptions", "three-statement-guide",
          "unit-economics-guide", "cash-runway-guide", "business-plan-guide"]


def test_expected_profiles():
    assert {p.name for p in PROFILES} == {"blank", "edtech"}


def test_profile_files_present():
    for p in PROFILES:
        for f in ("profile.json", "company.md", "metrics.md", "inputs.json"):
            assert (p / f).is_file(), (p.name, f)
        json.loads((p / "profile.json").read_text(encoding="utf-8"))["description"]


def test_profile_inputs_valid(tmp_path):
    for p in PROFILES:
        parse_inputs(json.loads((p / "inputs.json").read_text(encoding="utf-8")))
        r = subprocess.run([sys.executable, str(PLUGIN / "kernel" / "run.py"), "build", str(p / "inputs.json"),
                            "--out", str(tmp_path / p.name), "--no-xlsx"], capture_output=True, text=True)
        assert r.returncode in (0, 1), (p.name, r.stderr)


def test_edtech_profile_matches_fixture():
    a = json.loads((PLUGIN / "profiles" / "edtech" / "inputs.json").read_text(encoding="utf-8"))
    b = json.loads((ROOT / "tests" / "fixtures" / "edtech_inputs.json").read_text(encoding="utf-8"))
    assert a == b


def test_templates_and_skills_exist():
    for f in ("company.md", "metrics.md", "assumptions.md", "local/rules.md"):
        assert (PLUGIN / "templates" / f).is_file(), f
    for s in SKILLS:
        assert (PLUGIN / "skills" / s / "SKILL.md").is_file(), s
