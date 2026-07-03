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
        proxy_server="http://127.0.0.1:7890",
    )

    assert state.title == "Codex 用量看板"
    assert state.credits[0].granted_at == "2026-07-02 04:03:58"
    assert state.windows[0].remaining_percent == 37
    assert state.windows[1].remaining_percent == 57
    assert state.status_text == "最近刷新：2026-07-03 10:00:00"


def test_browser_fallback_contract_renders_dashboard_html():
    desktop_widget = load_module("desktop_widget", "desktop_widget.py")

    state = desktop_widget.WidgetState(
        title="Codex 用量看板",
        subtitle="重置卡、5 小时余量、周余量",
        credits=[
            desktop_widget.CreditDisplay(
                index=1,
                granted_at="2026-07-02 04:03:58",
                expires_at="2026-08-01 04:03:58",
            )
        ],
        windows=[
            desktop_widget.WindowDisplay(
                name="5小时窗口",
                remaining_percent=35,
                used_percent=65,
                reset_at="2026-07-03 14:57:56",
            ),
            desktop_widget.WindowDisplay(
                name="周窗口",
                remaining_percent=57,
                used_percent=43,
                reset_at="2026-07-07 20:16:41",
            ),
        ],
        proxy_server="http://127.0.0.1:7890",
        status_text="最近刷新：2026-07-03 12:00:00",
        status_color="#027a48",
        error_message=None,
    )

    html_text = desktop_widget.render_browser_html(state, 600)

    assert 'http-equiv="refresh" content="600"' in html_text
    assert "Codex 用量看板" in html_text
    assert "prefers-color-scheme: dark" in html_text
    assert "应用代理" in html_text
    assert "width:57%" in html_text


def test_tray_title_contract_exposes_remaining_percent():
    desktop_widget = load_module("desktop_widget", "desktop_widget.py")

    title = desktop_widget.format_tray_title(
        desktop_widget.WidgetState(
            title="Codex 用量看板",
            subtitle="",
            credits=[],
            windows=[
                desktop_widget.WindowDisplay(
                    name="5小时窗口",
                    remaining_percent=35,
                    used_percent=65,
                    reset_at="2026-07-03 14:57:56",
                )
            ],
            proxy_server="",
            status_text="ok",
            status_color="#4ade80",
            error_message=None,
        )
    )

    assert "5小时窗口35%" in title
