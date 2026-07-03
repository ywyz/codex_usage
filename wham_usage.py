#!/usr/bin/env python3
"""Query Codex WHAM rate-limit credits and usage with local auth credentials."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import socket
import ssl
import struct
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from http.client import HTTPSConnection
from pathlib import Path
from typing import Any


BEIJING_OFFSET = timedelta(hours=8)
DOT_DEFAULT_PORT = 853


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


def get_settings_path() -> Path:
    return Path.home() / ".codex-usage-widget.json"


def load_settings() -> dict[str, str]:
    path = get_settings_path()
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def save_settings(
    proxy_server: str | None = None,
    dot_server: str | None = None,
) -> None:
    payload = load_settings()
    if proxy_server is not None:
        payload["proxy_server"] = proxy_server
    if dot_server is not None:
        payload["dot_server"] = dot_server
    get_settings_path().write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="查询 Codex 账户的 rate-limit reset credits 与 WHAM 用量。"
    )
    parser.add_argument(
        "--auth-file",
        default=str(Path.home() / ".codex" / "auth.json"),
        help="auth.json 路径，默认读取 ~/.codex/auth.json",
    )
    parser.add_argument(
        "--proxy-server",
        help="代理地址，例如 http://127.0.0.1:7890。未传时自动读取本机配置或环境变量代理。",
    )
    parser.add_argument(
        "--dot-server",
        help="DoT 服务器地址。未传时自动读取本机配置或环境变量。",
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


def resolve_proxy(proxy_server: str | None = None) -> str | None:
    if proxy_server:
        return proxy_server

    settings_proxy = load_settings().get("proxy_server")
    if settings_proxy:
        return settings_proxy

    for key in (
        "HTTPS_PROXY",
        "https_proxy",
        "HTTP_PROXY",
        "http_proxy",
        "ALL_PROXY",
        "all_proxy",
    ):
        value = os.environ.get(key)
        if value:
            return value
    return None


def resolve_dot_server(dot_server: str | None = None) -> str | None:
    if dot_server:
        return dot_server

    settings_dot = load_settings().get("dot_server")
    if settings_dot:
        return settings_dot

    for key in ("CODEX_USAGE_DOT_SERVER", "codex_usage_dot_server"):
        value = os.environ.get(key)
        if value:
            return value
    return None


def parse_host_port(address: str, default_port: int) -> tuple[str, int]:
    if address.startswith("[") and "]" in address:
        host, _, port_text = address[1:].partition("]")
        port = default_port
        if port_text.startswith(":"):
            port = int(port_text[1:])
        return host, port
    if address.count(":") == 1 and "." in address:
        host, port_text = address.rsplit(":", 1)
        if port_text.isdigit():
            return host, int(port_text)
    return address, default_port


def encode_dns_name(hostname: str) -> bytes:
    labels = hostname.strip(".").split(".")
    encoded = bytearray()
    for label in labels:
        label_bytes = label.encode("ascii")
        encoded.append(len(label_bytes))
        encoded.extend(label_bytes)
    encoded.append(0)
    return bytes(encoded)


def build_dns_query(hostname: str, query_id: int | None = None) -> bytes:
    message_id = query_id if query_id is not None else secrets.randbelow(65535)
    header = struct.pack("!HHHHHH", message_id, 0x0100, 1, 0, 0, 0)
    question = encode_dns_name(hostname) + struct.pack("!HH", 1, 1)
    return header + question


def skip_dns_name(message: bytes, offset: int) -> int:
    while True:
        if offset >= len(message):
            raise WhamUsageError("DoT 响应格式不合法")
        length = message[offset]
        if length == 0:
            return offset + 1
        if length & 0xC0 == 0xC0:
            return offset + 2
        offset += 1 + length


def parse_dns_response_for_a_record(message: bytes) -> str:
    if len(message) < 12:
        raise WhamUsageError("DoT 响应过短")
    _, flags, qdcount, ancount, _, _ = struct.unpack("!HHHHHH", message[:12])
    if flags & 0x000F:
        raise WhamUsageError("DoT 返回了 DNS 错误码")
    offset = 12
    for _ in range(qdcount):
        offset = skip_dns_name(message, offset)
        offset += 4
    for _ in range(ancount):
        offset = skip_dns_name(message, offset)
        if offset + 10 > len(message):
            raise WhamUsageError("DoT 回答区格式不合法")
        rtype, rclass, _, rdlength = struct.unpack("!HHIH", message[offset : offset + 10])
        offset += 10
        rdata = message[offset : offset + rdlength]
        offset += rdlength
        if rtype == 1 and rclass == 1 and rdlength == 4:
            return socket.inet_ntoa(rdata)
    raise WhamUsageError("DoT 未返回 IPv4 地址")


def resolve_hostname_via_dot(hostname: str, dot_server: str) -> str:
    dot_host, dot_port = parse_host_port(dot_server, DOT_DEFAULT_PORT)
    payload = build_dns_query(hostname)
    context = ssl.create_default_context()
    try:
        with socket.create_connection((dot_host, dot_port), timeout=20) as sock:
            with context.wrap_socket(sock, server_hostname=dot_host) as tls_sock:
                tls_sock.sendall(struct.pack("!H", len(payload)) + payload)
                length_data = tls_sock.recv(2)
                if len(length_data) != 2:
                    raise WhamUsageError("DoT 响应长度头缺失")
                response_length = struct.unpack("!H", length_data)[0]
                response = bytearray()
                while len(response) < response_length:
                    chunk = tls_sock.recv(response_length - len(response))
                    if not chunk:
                        raise WhamUsageError("DoT 响应被提前关闭")
                    response.extend(chunk)
    except OSError as exc:
        raise WhamUsageError(f"DoT 解析失败: {exc}") from exc

    return parse_dns_response_for_a_record(bytes(response))


class DnsOverTlsClient:
    def __init__(self, dot_server: str) -> None:
        self.dot_server = dot_server

    def request_json(self, url: str, headers: dict[str, str]) -> dict[str, Any]:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise WhamUsageError("当前只支持通过 DoT 访问 HTTPS 地址")
        ip_address = resolve_hostname_via_dot(parsed.hostname, self.dot_server)
        return self._request_https_by_ip(parsed, ip_address, headers)

    def _request_https_by_ip(
        self,
        parsed: urllib.parse.ParseResult,
        ip_address: str,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        port = parsed.port or 443
        host = parsed.hostname
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        context = ssl.create_default_context()
        connection = HTTPSConnection(
            host=ip_address,
            port=port,
            timeout=30,
            context=context,
        )
        try:
            sock = socket.create_connection((ip_address, port), timeout=30)
            connection.sock = context.wrap_socket(sock, server_hostname=host)
            request_headers = {
                "Host": host,
                "Accept": "application/json",
                "User-Agent": "codex-wham-usage/1.0",
                **headers,
            }
            connection.request("GET", path, headers=request_headers)
            response = connection.getresponse()
            body = response.read().decode("utf-8", errors="replace")
            if response.status == 401:
                raise WhamUsageError("401：凭证失效或没带对 Authorization header")
            if response.status >= 400:
                raise WhamUsageError(f"请求失败，HTTP {response.status}: {body[:300]}")
            return json.loads(body)
        finally:
            connection.close()


def build_url_opener(proxy_server: str | None = None) -> urllib.request.OpenerDirector:
    resolved_proxy = resolve_proxy(proxy_server)
    if not resolved_proxy:
        return urllib.request.build_opener()

    return urllib.request.build_opener(
        urllib.request.ProxyHandler(
            {
                "http": resolved_proxy,
                "https": resolved_proxy,
            }
        )
    )


def request_json(
    url: str,
    headers: dict[str, str],
    proxy_server: str | None = None,
    dot_server: str | None = None,
) -> dict[str, Any]:
    resolved_proxy = resolve_proxy(proxy_server)
    resolved_dot = resolve_dot_server(dot_server)
    if resolved_dot and not resolved_proxy:
        return DnsOverTlsClient(resolved_dot).request_json(url, headers)

    request = urllib.request.Request(
        url,
        headers={
            "Authorization": headers["Authorization"],
            "Accept": "application/json",
            "User-Agent": "codex-wham-usage/1.0",
            **(
                {}
                if "ChatGPT-Account-Id" not in headers
                else {"ChatGPT-Account-Id": headers["ChatGPT-Account-Id"]}
            ),
        },
    )
    opener = build_url_opener(proxy_server)
    try:
        with opener.open(request, timeout=30) as response:
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

    windows: list[UsageWindow] = []
    for label, key in (("5小时窗口", "primary_window"), ("周窗口", "secondary_window")):
        raw = rate_limit.get(key)
        if not isinstance(raw, dict):
            raise WhamUsageError(f"usage 响应缺少 {key}")
        used_percent = int(raw.get("used_percent", 0))
        reset_at = raw.get("reset_at")
        if not isinstance(reset_at, (int, float)):
            raise WhamUsageError(f"usage 响应里的 {key}.reset_at 缺失或格式不对")
        windows.append(
            UsageWindow(
                name=label,
                used_percent=used_percent,
                remaining_percent=max(0, 100 - used_percent),
                reset_at=utc_to_beijing_text(reset_at),
            )
        )
    return windows


def fetch_snapshot(
    auth_file: str,
    proxy_server: str | None = None,
    dot_server: str | None = None,
) -> UsageSnapshot:
    access_token, account_id = load_auth(auth_file)
    credits_payload = request_json(
        "https://chatgpt.com/backend-api/wham/rate-limit-reset-credits",
        headers={"Authorization": f"Bearer {access_token}"},
        proxy_server=proxy_server,
        dot_server=dot_server,
    )
    usage_payload = request_json(
        "https://chatgpt.com/backend-api/wham/usage",
        headers={
            "Authorization": f"Bearer {access_token}",
            "ChatGPT-Account-Id": account_id,
        },
        proxy_server=proxy_server,
        dot_server=dot_server,
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
        lines.append(f"{window.name}余额：{window.remaining_percent}%（已用 {window.used_percent}%）")
        lines.append(f"{window.name}重置时间：{window.reset_at}")

    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    try:
        snapshot = fetch_snapshot(args.auth_file, args.proxy_server, args.dot_server)
        print(build_report(snapshot.credits, snapshot.windows))
        return 0
    except WhamUsageError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
