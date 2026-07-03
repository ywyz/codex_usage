from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_linux_build_script_uses_pyinstaller_and_creates_tarball():
    script = (REPO_ROOT / "scripts/build_linux.sh").read_text(encoding="utf-8")

    assert "PyInstaller" in script
    assert "requirements-build.txt" in script
    assert ".tar.gz" in script
    assert "codex-usage-widget" in script


def test_windows_build_script_uses_pyinstaller_and_creates_zip():
    script = (REPO_ROOT / "scripts/build_windows.ps1").read_text(encoding="utf-8")

    assert "PyInstaller" in script
    assert "requirements-build.txt" in script
    assert ".zip" in script
    assert "codex-usage-widget.exe" in script


def test_package_workflow_builds_both_os_and_uploads_artifacts():
    workflow = (REPO_ROOT / ".github/workflows/package.yml").read_text(encoding="utf-8")

    assert "ubuntu-latest" in workflow
    assert "windows-latest" in workflow
    assert "upload-artifact" in workflow
    assert "scripts/build_linux.sh" in workflow
    assert "build_windows.ps1" in workflow
