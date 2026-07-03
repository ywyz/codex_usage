from __future__ import annotations

import importlib.util
import sys
from datetime import datetime
from pathlib import Path


def load_module(module_name: str, file_name: str):
    repo_root = Path(__file__).resolve().parents[1]
    module_path = repo_root / file_name
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_widget_state_contract_covers_required_desktop_fields():
    wham_usage = load_module("wham_usage", "wham_usage.py")
    desktop_widget = load_module("desktop_widget", "desktop_widget.py")

    state = desktop_widget.build_widget_state(
        snapshot=wham_usage.UsageSnapshot(
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
        ),
        error_message=None,
        fetched_at=datetime(2026, 7, 3, 10, 0, 0),
    )

    assert state.title == "Codex 用量看板"
    assert "发放：2026-07-02 04:03:58" in state.credit_lines
    assert "5小时窗口余量：37%" in state.usage_lines
    assert "周窗口余量：57%" in state.usage_lines
    assert state.status_text == "最近刷新：2026-07-03 10:00:00"


def test_browser_fallback_contract_renders_dashboard_html():
    desktop_widget = load_module("desktop_widget", "desktop_widget.py")

    state = desktop_widget.WidgetState(
        title="Codex 用量看板",
        subtitle="重置卡、5 小时余量、周余量",
        credit_lines=["第 1 张", "发放：2026-07-02 04:03:58"],
        usage_lines=["5小时窗口余量：35%", "周窗口余量：57%"],
        status_text="最近刷新：2026-07-03 12:00:00",
        status_color="#027a48",
    )

    html_text = desktop_widget.render_browser_html(state, 600)

    assert 'http-equiv="refresh" content="600"' in html_text
    assert "Codex 用量看板" in html_text
    assert "周窗口余量：57%" in html_text
