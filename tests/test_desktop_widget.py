from __future__ import annotations

import importlib.util
import sys
from datetime import datetime
from pathlib import Path

import pytest


def load_module(module_name: str, file_name: str):
    repo_root = Path(__file__).resolve().parents[1]
    module_path = repo_root / file_name
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


wham_usage = load_module("wham_usage", "wham_usage.py")
desktop_widget = load_module("desktop_widget", "desktop_widget.py")


def test_validate_refresh_seconds_limits_range():
    assert desktop_widget.validate_refresh_seconds(300) == 300
    assert desktop_widget.validate_refresh_seconds(600) == 600

    with pytest.raises(ValueError, match="300 到 600"):
        desktop_widget.validate_refresh_seconds(299)


def test_build_widget_state_for_success_snapshot():
    snapshot = wham_usage.UsageSnapshot(
        credits=[
            wham_usage.CreditWindow(
                granted_at="2026-07-02 04:03:58",
                expires_at="2026-08-01 04:03:58",
            )
        ],
        windows=[
            wham_usage.UsageWindow(
                name="5小时窗口",
                used_percent=63,
                remaining_percent=37,
                reset_at="2026-07-03 14:57:56",
            ),
            wham_usage.UsageWindow(
                name="周窗口",
                used_percent=43,
                remaining_percent=57,
                reset_at="2026-07-07 20:16:41",
            ),
        ],
    )

    state = desktop_widget.build_widget_state(
        snapshot=snapshot,
        error_message=None,
        fetched_at=datetime(2026, 7, 3, 10, 0, 0),
    )

    assert state.credit_lines[0] == "第 1 张"
    assert "5小时窗口余量：37%" in state.usage_lines
    assert state.status_text == "最近刷新：2026-07-03 10:00:00"


def test_build_widget_state_for_error():
    state = desktop_widget.build_widget_state(
        snapshot=None,
        error_message="401：凭证失效或没带对 Authorization header",
        fetched_at=None,
    )

    assert state.subtitle == "数据刷新失败"
    assert state.status_color == "#b42318"
    assert "无法读取重置卡信息" in state.credit_lines
