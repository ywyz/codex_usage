#!/usr/bin/env python3
"""Query Codex WHAM rate-limit credits and usage with local auth credentials."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


BEIJING_OFFSET = timedelta(hours=8)


class WhamUsageError(RuntimeError):
    """Raised when auth loading or API calls fail."""


@dataclass(frozen=True)
class CreditWindow:
    granted_at: str
    expires_at: str


@dataclass(frozen=True)
class UsageWindow:
    name: str
    used_percent: int
    remaining_percent: int
    reset_at: str


@dataclass(frozen=True)
class UsageSnapshot:
    credits: list[CreditWindow]
    windows: list[UsageWindow]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="查询 Codex 账户的 rate-limit reset credits 与 WHAM 用量。"
    )
    parser.add_argument(
        "--auth-file",
        default=str(Path.home() / ".codex" / "auth.json"),
        help="auth.json 路径，默认读取 ~/.codex/auth.json",
    )
    return parser.parse_args()


def load_auth(auth_file: str) -> tuple[str, str]:
    try:
        payload = json.loads(Path(auth_file).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise WhamUsageError(f"认证文件不存在: {auth_file}") from exc
    except json.JSONDecodeError as exc:
        raise WhamUsageError(f"认证文件不是合法 JSON: {auth_file}") from exc

    tokens = payload.get("tokens") or {}
    access_token = tokens.get("access_token")
    account_id = tokens.get("account_id")

    if not access_token:
        raise WhamUsageError("auth.json 中缺少 tokens.access_token")
    if not account_id:
        raise WhamUsageError("auth.json 中缺少 tokens.account_id")

    return str(access_token), str(account_id)


def utc_to_beijing_text(value: str | int | float) -> str:
    if isinstance(value, str):
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        dt = datetime.fromtimestamp(value, tz=UTC)
    beijing = dt.astimezone(UTC) + BEIJING_OFFSET
    return beijing.strftime("%Y-%m-%d %H:%M:%S")


def request_json(url: str, headers: dict[str, str]) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": headers["Authorization"],
            "Accept": "application/json",
            "User-Agent": "codex-wham-usage/1.0",
            **({} if "ChatGPT-Account-Id" not in headers else {"ChatGPT-Account-Id": headers["ChatGPT-Account-Id"]}),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise WhamUsageError("401：凭证失效或没带对 Authorization header") from exc
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise WhamUsageError(f"请求失败，HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise WhamUsageError(f"网络请求失败: {exc.reason}") from exc


def parse_credits(payload: dict[str, Any]) -> list[CreditWindow]:
    credits = payload.get("credits")
    if not isinstance(credits, list):
        return []
    parsed: list[CreditWindow] = []
    for item in credits:
        if not isinstance(item, dict):
            continue
        granted_at = item.get("granted_at")
        expires_at = item.get("expires_at")
        if isinstance(granted_at, str) and isinstance(expires_at, str):
            parsed.append(
                CreditWindow(
                    granted_at=utc_to_beijing_text(granted_at),
                    expires_at=utc_to_beijing_text(expires_at),
                )
            )
    return parsed


def parse_usage_windows(payload: dict[str, Any]) -> list[UsageWindow]:
    rate_limit = payload.get("rate_limit")
    if not isinstance(rate_limit, dict):
        raise WhamUsageError("usage 响应缺少 rate_limit")

    window_specs = [
        ("5小时窗口", "primary_window"),
        ("周窗口", "secondary_window"),
    ]
    windows: list[UsageWindow] = []
    for label, key in window_specs:
        raw = rate_limit.get(key)
        if not isinstance(raw, dict):
            raise WhamUsageError(f"usage 响应缺少 {key}")
        used_percent = int(raw.get("used_percent", 0))
        reset_at = raw.get("reset_at")
        if not isinstance(reset_at, (int, float)):
            raise WhamUsageError(f"usage 响应里的 {key}.reset_at 缺失或格式不对")
        remaining_percent = max(0, 100 - used_percent)
        windows.append(
            UsageWindow(
                name=label,
                used_percent=used_percent,
                remaining_percent=remaining_percent,
                reset_at=utc_to_beijing_text(reset_at),
            )
        )
    return windows


def fetch_snapshot(auth_file: str) -> UsageSnapshot:
    access_token, account_id = load_auth(auth_file)
    credits_payload = request_json(
        "https://chatgpt.com/backend-api/wham/rate-limit-reset-credits",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    usage_payload = request_json(
        "https://chatgpt.com/backend-api/wham/usage",
        headers={
            "Authorization": f"Bearer {access_token}",
            "ChatGPT-Account-Id": account_id,
        },
    )
    return UsageSnapshot(
        credits=parse_credits(credits_payload),
        windows=parse_usage_windows(usage_payload),
    )


def build_report(credits: list[CreditWindow], windows: list[UsageWindow]) -> str:
    lines = ["重置卡："]
    if credits:
        for index, credit in enumerate(credits, start=1):
            lines.append(f"第 {index} 张")
            lines.append(f"发放时间：{credit.granted_at}")
            lines.append(f"过期时间：{credit.expires_at}")
    else:
        lines.append("当前没有可展示的重置卡。")

    lines.append("")
    lines.append("用量窗口：")
    for window in windows:
        lines.append(
            f"{window.name}余额：{window.remaining_percent}%（已用 {window.used_percent}%）"
        )
        lines.append(f"{window.name}重置时间：{window.reset_at}")

    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    try:
        snapshot = fetch_snapshot(args.auth_file)
        report = build_report(snapshot.credits, snapshot.windows)
        print(report)
        return 0
    except WhamUsageError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
