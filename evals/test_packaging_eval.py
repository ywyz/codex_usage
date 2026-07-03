from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_packaging_docs_and_workflow_match_expected_delivery():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    workflow = (REPO_ROOT / ".github/workflows/package.yml").read_text(encoding="utf-8")

    assert "## 打包" in readme
    assert "scripts/build_linux.sh" in readme
    assert "scripts/build_windows.ps1" in readme
    assert "Artifacts" in readme
    assert "ubuntu-latest" in workflow
    assert "windows-latest" in workflow
