#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VERSION_TAG="${VERSION_TAG:-$(date +%Y%m%d-%H%M%S)}"
ARTIFACT_DIR="$ROOT_DIR/release/linux"
DIST_DIR="$ROOT_DIR/dist"
BUILD_VENV_DIR="$ROOT_DIR/.venv-build"
ARCHIVE_BASENAME="codex-usage-widget-linux-x86_64-${VERSION_TAG}"
ARCHIVE_DIR="$ARTIFACT_DIR/$ARCHIVE_BASENAME"

cd "$ROOT_DIR"

mkdir -p "$ARTIFACT_DIR"
"$PYTHON_BIN" -m venv "$BUILD_VENV_DIR"
"$BUILD_VENV_DIR/bin/python" -m pip install --upgrade pip
"$BUILD_VENV_DIR/bin/python" -m pip install -r packaging/requirements-build.txt
"$BUILD_VENV_DIR/bin/python" -m PyInstaller --clean --noconfirm packaging/codex_usage_widget.spec

rm -rf "$ARCHIVE_DIR"
mkdir -p "$ARCHIVE_DIR"
cp "$DIST_DIR/codex-usage-widget" "$ARCHIVE_DIR/"
cp README.md "$ARCHIVE_DIR/"

tar -C "$ARTIFACT_DIR" -czf "$ARTIFACT_DIR/${ARCHIVE_BASENAME}.tar.gz" "$ARCHIVE_BASENAME"

printf 'Linux package created: %s\n' "$ARTIFACT_DIR/${ARCHIVE_BASENAME}.tar.gz"
