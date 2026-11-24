"""Check that local installs and Vercel get the same pinned packages."""

import tomllib
from pathlib import Path

ROOT: Path = Path(__file__).resolve().parents[1]


def test_one_pinned_list() -> None:
    """Vercel reads pyproject.toml; pip reads requirements.txt; they must match."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    lines = (ROOT / "requirements.txt").read_text().splitlines()
    pins = [line.strip() for line in lines if line.strip()]
    assert sorted(project["dependencies"]) == sorted(pins)
    assert all("==" in pin for pin in pins)
