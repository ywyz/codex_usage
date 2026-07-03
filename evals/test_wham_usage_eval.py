from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_module():
    repo_root = Path(__file__).resolve().parents[1]
    module_path = repo_root / "wham_usage.py"
    spec = importlib.util.spec_from_file_location("wham_usage", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_report_contract_matches_requested_chinese_output():
    wham_usage = load_module()

    report = wham_usage.build_report(
        credits=[
            wham_usage.CreditWindow(
                granted_at="2026-07-02 04:03:58",
                expires_at="2026-08-01 04:03:58",
            )
        ],
        windows=[
            wham_usage.UsageWindow(
                name="5小时窗口",
                used_percent=58,
                remaining_percent=42,
                reset_at="2026-07-03 14:57:56",
            ),
            wham_usage.UsageWindow(
                name="周窗口",
                used_percent=42,
                remaining_percent=58,
                reset_at="2026-07-07 20:16:41",
            ),
        ],
    )

    assert "重置卡：" in report
    assert "发放时间：2026-07-02 04:03:58" in report
    assert "过期时间：2026-08-01 04:03:58" in report
    assert "5小时窗口余额：42%（已用 58%）" in report
    assert "5小时窗口重置时间：2026-07-03 14:57:56" in report
    assert "周窗口余额：58%（已用 42%）" in report
    assert "周窗口重置时间：2026-07-07 20:16:41" in report


def test_proxy_resolution_contract_prefers_cli_then_environment(monkeypatch):
    wham_usage = load_module()

    monkeypatch.setenv("HTTPS_PROXY", "http://env-proxy:7890")

    assert wham_usage.resolve_proxy("http://cli-proxy:7890") == "http://cli-proxy:7890"
    assert wham_usage.resolve_proxy() == "http://env-proxy:7890"
