import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins" / "finance-soul"
AGENT_FIELDS = {"name", "description", "tools", "model", "skills"}


def frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), path
    block = text.split("---\n", 2)[1]
    out = {}
    for line in block.splitlines():
        if line and not line.startswith(" ") and ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip().strip('"')
    return out


def agent_files():
    return sorted(p for p in (PLUGIN / "agents").glob("*.md") if not p.name.startswith("._"))


def skill_files():
    return sorted(p for p in (PLUGIN / "skills").glob("*/SKILL.md") if not p.parent.name.startswith("._"))


def test_manifests():
    plugin = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert plugin["name"] == "finance-soul"
    market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    assert market["plugins"][0]["name"] == "finance-soul"
    assert market["plugins"][0]["source"] == "./plugins/finance-soul"


def test_frontmatter():
    for p in agent_files():
        fm = frontmatter(p)
        assert fm["name"] == p.stem, p
        assert set(fm) <= AGENT_FIELDS, (p, set(fm) - AGENT_FIELDS)
        assert english_description(fm["description"]), p
    for p in skill_files():
        fm = frontmatter(p)
        assert fm["name"] == p.parent.name, p
        assert english_description(fm["description"]), p


def english_description(d: str) -> bool:
    """English text; Russian trigger phrases are allowed only inside quotes."""
    outside_quotes = re.sub(r'"[^"]*"', "", d)
    return len(d) > 20 and outside_quotes.isascii()


def test_core_budget():
    assert len((PLUGIN / "hooks" / "soul-core.md").read_text(encoding="utf-8")) < 6000


def test_references_exist():
    skills = {p.parent.name for p in skill_files()}
    agents = {p.stem for p in agent_files()}
    assert agents == {"model-builder", "model-auditor", "cfo-reviewer"}
    known = skills | agents
    files = [p for p in PLUGIN.rglob("*.md") if not p.name.startswith("._")]
    for p in files:
        for ref in re.findall(r"finance-soul:([a-z0-9-]+)", p.read_text(encoding="utf-8")):
            assert ref in known, (p, ref)


def test_no_macos_appledouble_files_tracked():
    """._* files from macOS on external drives show up as extra agents and skills."""
    import subprocess
    files = subprocess.run(["git", "ls-files"], cwd=str(ROOT), capture_output=True, text=True).stdout.split()
    assert [f for f in files if Path(f).name.startswith("._")] == []
