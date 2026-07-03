from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


def load_module():
    repo_root = Path(__file__).resolve().parents[1]
    module_path = repo_root / "wham_usage.py"
    spec = importlib.util.spec_from_file_location("wham_usage", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


wham_usage = load_module()


def test_load_auth_reads_token_and_account_id(tmp_path: Path):
    auth_file = tmp_path / "auth.json"
    auth_file.write_text(
        json.dumps(
            {
                "tokens": {
                    "access_token": "test-token",
                    "account_id": "account-123",
                }
            }
        ),
        encoding="utf-8",
    )

    access_token, account_id = wham_usage.load_auth(str(auth_file))

    assert access_token == "test-token"
    assert account_id == "account-123"


def test_load_auth_rejects_missing_account_id(tmp_path: Path):
    auth_file = tmp_path / "auth.json"
    auth_file.write_text(json.dumps({"tokens": {"access_token": "test-token"}}), encoding="utf-8")

    with pytest.raises(wham_usage.WhamUsageError, match="tokens.account_id"):
        wham_usage.load_auth(str(auth_file))


def test_parse_credits_converts_utc_to_beijing():
    credits = wham_usage.parse_credits(
        {
            "credits": [
                {
                    "granted_at": "2026-07-01T20:03:58.215399Z",
                    "expires_at": "2026-07-31T20:03:58.215399Z",
                }
            ]
        }
    )

    assert credits == [
        wham_usage.CreditWindow(
            granted_at="2026-07-02 04:03:58",
            expires_at="2026-08-01 04:03:58",
        )
    ]


def test_parse_usage_windows_maps_primary_and_secondary_windows():
    windows = wham_usage.parse_usage_windows(
        {
            "rate_limit": {
                "primary_window": {
                    "used_percent": 58,
                    "reset_at": 1783061876,
                },
                "secondary_window": {
                    "used_percent": 42,
                    "reset_at": 1783426601,
                },
            }
        }
    )

    assert windows == [
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
    ]


def test_build_report_only_contains_expected_fields():
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

    assert "2026-07-02 04:03:58" in report
    assert "5小时窗口余额：42%（已用 58%）" in report
    assert "周窗口重置时间：2026-07-07 20:16:41" in report
    assert "access_token" not in report
    assert "refresh_token" not in report


def test_fetch_snapshot_delegates_to_parsers(monkeypatch):
    credits_payload = {"credits": [{"granted_at": "2026-07-01T20:03:58.215399Z", "expires_at": "2026-07-31T20:03:58.215399Z"}]}
    usage_payload = {
        "rate_limit": {
            "primary_window": {"used_percent": 58, "reset_at": 1783061876},
            "secondary_window": {"used_percent": 42, "reset_at": 1783426601},
        }
    }

    monkeypatch.setattr(wham_usage, "load_auth", lambda path: ("token", "account"))
    calls = []

    def fake_request_json(url, headers):
        calls.append((url, headers))
        if url.endswith("rate-limit-reset-credits"):
            return credits_payload
        return usage_payload

    monkeypatch.setattr(wham_usage, "request_json", fake_request_json)

    snapshot = wham_usage.fetch_snapshot("/tmp/auth.json")

    assert len(calls) == 2
    assert snapshot.credits[0].granted_at == "2026-07-02 04:03:58"
    assert snapshot.windows[0].remaining_percent == 42
