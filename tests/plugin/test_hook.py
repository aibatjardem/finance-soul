import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / "plugins" / "finance-soul" / "hooks" / "session-start"
BUDGET = 9000


def run_hook(project: Path) -> str:
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(project))
    r = subprocess.run(["bash", str(HOOK)], capture_output=True, text=True, env=env, cwd=str(project))
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    ctx = data["hookSpecificOutput"]["additionalContext"]
    assert data["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert len(ctx) < BUDGET
    return ctx


def test_hook_no_finsoul(tmp_path):
    ctx = run_hook(tmp_path)
    assert "/finance-soul:setup" in ctx
    assert "Числа считает ядро" in ctx  # the compact soul is there


def test_hook_with_finsoul_lists_models(tmp_path):
    fs = tmp_path / ".finsoul"
    (fs / "models" / "m1").mkdir(parents=True)
    (fs / "company.md").write_text("# Компания\n\nОтрасль: EdTech\n", encoding="utf-8")
    (fs / "metrics.md").write_text("TBD\n", encoding="utf-8")
    (fs / "models" / "m1" / "inputs.json").write_text("{}", encoding="utf-8")
    ctx = run_hook(tmp_path)
    assert "m1" in ctx
    assert ".finsoul/company.md" in ctx
    assert "metrics.md" in ctx and "TBD" in ctx


def test_hook_inlines_local_rules(tmp_path):
    (tmp_path / ".finsoul" / "local").mkdir(parents=True)
    (tmp_path / ".finsoul" / "local" / "rules.md").write_text("Отчёты только в млн тенге", encoding="utf-8")
    assert "Отчёты только в млн тенге" in run_hook(tmp_path)


def test_hook_ignores_symlink(tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("SECRET-VALUE", encoding="utf-8")
    (tmp_path / ".finsoul" / "local").mkdir(parents=True)
    os.symlink(secret, tmp_path / ".finsoul" / "local" / "x.md")
    assert "SECRET-VALUE" not in run_hook(tmp_path)


def test_hook_huge_local_file_stays_in_budget(tmp_path):
    (tmp_path / ".finsoul" / "local").mkdir(parents=True)
    (tmp_path / ".finsoul" / "local" / "big.md").write_text("ж" * 50000, encoding="utf-8")
    ctx = run_hook(tmp_path)
    assert "big.md" in ctx


def test_hook_reports_kernel_path(tmp_path):
    ctx = run_hook(tmp_path)
    kernel = HOOK.parent.parent / "kernel" / "run.py"
    assert str(kernel.resolve()) in ctx


def test_hook_runs_via_hooks_json_without_exec_bit(tmp_path):
    """Plugins installed from git may lose the executable bit (exFAT, core.fileMode=false):
    the hooks.json command must still work, exactly as Claude Code runs it."""
    import shutil
    import stat
    copy = tmp_path / "plugin"
    shutil.copytree(HOOK.parent, copy / "hooks")
    for f in (copy / "hooks").iterdir():
        f.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
    cmd = json.loads((copy / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    project = tmp_path / "proj"
    project.mkdir()
    env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(copy), CLAUDE_PROJECT_DIR=str(project))
    r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, cwd=str(project))
    assert r.returncode == 0, r.stderr
    assert "/finance-soul:setup" in json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]


def test_scripts_executable_in_git():
    out = subprocess.run(["git", "ls-files", "-s", "plugins/finance-soul/hooks/session-start",
                          "plugins/finance-soul/hooks/run-hook.cmd", "plugins/finance-soul/kernel/run.py"],
                         cwd=str(ROOT), capture_output=True, text=True).stdout.splitlines()
    assert len(out) == 3
    assert all(line.startswith("100755") for line in out), out
