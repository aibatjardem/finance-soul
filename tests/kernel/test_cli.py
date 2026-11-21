import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "plugins" / "finance-soul" / "kernel" / "run.py"
FIXTURE = ROOT / "tests" / "fixtures" / "edtech_inputs.json"


def cli(*args, cwd=None):
    return subprocess.run([sys.executable, str(RUN), *args], capture_output=True, text=True, cwd=cwd)


def test_build_writes_three_files(tmp_path):
    r = cli("build", str(FIXTURE), "--out", str(tmp_path))
    assert r.returncode == 0, r.stderr
    for name in ("report.md", "checks.json", "model.xlsx"):
        assert (tmp_path / name).exists(), name
    report = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "## Итог" in report and "## Сценарии" in report
    assert "не является финансовой" in report.lower()
    checks = json.loads((tmp_path / "checks.json").read_text(encoding="utf-8"))
    assert checks["errors"] == []
    assert set(checks["scenario_results"]) == {"base", "upside", "downside"}


def test_no_xlsx_flag(tmp_path):
    r = cli("build", str(FIXTURE), "--out", str(tmp_path), "--no-xlsx")
    assert r.returncode == 0
    assert not (tmp_path / "model.xlsx").exists()


def test_bad_input_exit_2_without_traceback(tmp_path):
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    del data["revenue_streams"][0]["price"]
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    r = cli("build", str(bad), "--out", str(tmp_path / "o"))
    assert r.returncode == 2
    assert "revenue_streams[0].price" in r.stderr
    assert "Traceback" not in r.stderr


def test_missing_file_exit_2(tmp_path):
    r = cli("build", str(tmp_path / "nope.json"), "--out", str(tmp_path))
    assert r.returncode == 2 and "не найден" in r.stderr


def test_undefined_irr_reads_naturally(tmp_path):
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    data["revenue_streams"][0]["price"] = 3000
    p = tmp_path / "flat.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    r = cli("build", str(p), "--out", str(tmp_path / "o"), "--no-xlsx")
    assert r.returncode == 0
    assert "не определена" in (tmp_path / "o" / "report.md").read_text(encoding="utf-8")


def test_check_env():
    r = cli("check-env")
    assert r.returncode == 0
    assert "Python" in r.stdout and "openpyxl" in r.stdout


def test_runs_from_any_cwd(tmp_path):
    r = cli("build", str(FIXTURE), "--out", str(tmp_path / "o"), "--no-xlsx", cwd=str(tmp_path))
    assert r.returncode == 0, r.stderr


def test_markdown_tables_well_formed(tmp_path):
    r = cli("build", str(FIXTURE), "--out", str(tmp_path), "--no-xlsx")
    assert r.returncode == 0
    report = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "||" not in report
    assert "|---|---:|---:|---:|" in report  # three scenario columns, three P&L years


def _write(tmp_path, data, name="in.json"):
    p = tmp_path / name
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


def test_long_horizon_builds(tmp_path):
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    data["months"] = 120
    r = cli("build", str(_write(tmp_path, data)), "--out", str(tmp_path / "o"), "--no-xlsx")
    assert r.returncode == 0, r.stderr


def test_non_utf8_and_directory_inputs_exit_2(tmp_path):
    bad = tmp_path / "cp1251.json"
    bad.write_bytes('{"name": "Школа"}'.encode("cp1251"))
    for target in (bad, tmp_path):
        r = cli("build", str(target), "--out", str(tmp_path / "o"))
        assert r.returncode == 2, (target, r.stderr)
        assert "Traceback" not in r.stderr


def test_unexpected_failure_exit_3(monkeypatch, capsys, tmp_path):
    from finsoul import cli as cli_mod

    def boom(mi):
        raise RuntimeError("неожиданно")

    monkeypatch.setattr(cli_mod, "run_scenarios", boom)
    code = cli_mod.main(["build", str(FIXTURE), "--out", str(tmp_path / "o"), "--no-xlsx"])
    assert code == 3
    err = capsys.readouterr().err
    assert "неожиданно" in err and "Traceback" not in err
    assert not (tmp_path / "o" / "report.md").exists()
