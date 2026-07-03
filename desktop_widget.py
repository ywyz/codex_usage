#!/usr/bin/env python3
"""Desktop widget for Codex WHAM usage on Ubuntu and Windows."""

from __future__ import annotations

import argparse
import html
import threading
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TYPE_CHECKING

from wham_usage import UsageSnapshot, WhamUsageError, fetch_snapshot

if TYPE_CHECKING:
    import tkinter as tk
    from tkinter import ttk


DEFAULT_REFRESH_SECONDS = 300
MAX_REFRESH_SECONDS = 600
MIN_REFRESH_SECONDS = 300


@dataclass(frozen=True)
class WidgetState:
    title: str
    subtitle: str
    credit_lines: list[str]
    usage_lines: list[str]
    status_text: str
    status_color: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="桌面显示 Codex 重置卡、5 小时余量和周余量。"
    )
    parser.add_argument(
        "--auth-file",
        default=str(Path.home() / ".codex" / "auth.json"),
        help="auth.json 路径，默认读取 ~/.codex/auth.json",
    )
    parser.add_argument(
        "--refresh-seconds",
        type=int,
        default=DEFAULT_REFRESH_SECONDS,
        help="刷新间隔，单位秒，必须在 300 到 600 之间，默认 300",
    )
    parser.add_argument(
        "--proxy-server",
        help="代理地址，例如 http://127.0.0.1:7890。未传时自动读取环境变量代理。",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="浏览器回退模式下不自动打开浏览器，只打印本地地址。",
    )
    return parser.parse_args()


def validate_refresh_seconds(seconds: int) -> int:
    if seconds < MIN_REFRESH_SECONDS or seconds > MAX_REFRESH_SECONDS:
        raise ValueError("刷新间隔必须在 300 到 600 秒之间")
    return seconds


def build_widget_state(
    snapshot: UsageSnapshot | None,
    error_message: str | None,
    fetched_at: datetime | None,
) -> WidgetState:
    if error_message:
        return WidgetState(
            title="Codex 用量看板",
            subtitle="数据刷新失败",
            credit_lines=["无法读取重置卡信息"],
            usage_lines=["请检查本机 Codex 凭证、代理或网络连接"],
            status_text=error_message,
            status_color="#b42318",
        )

    assert snapshot is not None
    credit_lines: list[str] = []
    if snapshot.credits:
        for index, credit in enumerate(snapshot.credits, start=1):
            credit_lines.append(f"第 {index} 张")
            credit_lines.append(f"发放：{credit.granted_at}")
            credit_lines.append(f"过期：{credit.expires_at}")
    else:
        credit_lines.append("当前没有可展示的重置卡")

    usage_lines = []
    for window in snapshot.windows:
        usage_lines.append(f"{window.name}余量：{window.remaining_percent}%")
        usage_lines.append(f"{window.name}重置：{window.reset_at}")

    stamp = fetched_at.strftime("%Y-%m-%d %H:%M:%S") if fetched_at else "未知"
    return WidgetState(
        title="Codex 用量看板",
        subtitle="重置卡、5 小时余量、周余量",
        credit_lines=credit_lines,
        usage_lines=usage_lines,
        status_text=f"最近刷新：{stamp}",
        status_color="#027a48",
    )


def load_tk_modules():
    try:
        import tkinter as tk
        from tkinter import ttk
    except ModuleNotFoundError:
        return None, None
    return tk, ttk


class CodexUsageWidget:
    def __init__(
        self,
        auth_file: str,
        refresh_seconds: int,
        proxy_server: str | None,
    ) -> None:
        tk, ttk = load_tk_modules()
        if tk is None or ttk is None:
            raise ModuleNotFoundError("No module named 'tkinter'", name="tkinter")

        self._tk = tk
        self._ttk = ttk
        self.auth_file = auth_file
        self.refresh_seconds = validate_refresh_seconds(refresh_seconds)
        self.proxy_server = proxy_server
        self.root = tk.Tk()
        self.root.title("Codex 用量看板")
        self.root.geometry("420x360")
        self.root.minsize(380, 320)
        self.root.configure(bg="#f5efe4")

        self.title_var = tk.StringVar(value="Codex 用量看板")
        self.subtitle_var = tk.StringVar(value="准备加载...")
        self.credits_var = tk.StringVar(value="读取中...")
        self.usage_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="正在初始化")

        self.status_label: ttk.Label
        self._refresh_job: str | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        ttk = self._ttk
        tk = self._tk
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Card.TFrame", background="#fffaf2")
        style.configure("CardTitle.TLabel", background="#fffaf2", foreground="#7a4b00")
        style.configure("Body.TLabel", background="#fffaf2", foreground="#1f2937")

        shell = ttk.Frame(self.root, padding=16, style="Card.TFrame")
        shell.pack(fill="both", expand=True, padx=12, pady=12)

        ttk.Label(
            shell,
            textvariable=self.title_var,
            font=("Segoe UI", 18, "bold"),
            style="CardTitle.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            shell,
            textvariable=self.subtitle_var,
            font=("Segoe UI", 10),
            style="Body.TLabel",
        ).pack(anchor="w", pady=(4, 16))

        ttk.Label(
            shell,
            text="重置卡",
            font=("Segoe UI", 12, "bold"),
            style="CardTitle.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            shell,
            textvariable=self.credits_var,
            justify="left",
            font=("Consolas", 11),
            style="Body.TLabel",
        ).pack(anchor="w", pady=(6, 16))

        ttk.Label(
            shell,
            text="用量窗口",
            font=("Segoe UI", 12, "bold"),
            style="CardTitle.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            shell,
            textvariable=self.usage_var,
            justify="left",
            font=("Consolas", 11),
            style="Body.TLabel",
        ).pack(anchor="w", pady=(6, 16))

        self.status_label = ttk.Label(
            shell,
            textvariable=self.status_var,
            font=("Segoe UI", 9),
            style="Body.TLabel",
        )
        self.status_label.pack(anchor="w")

        button_row = ttk.Frame(shell, style="Card.TFrame")
        button_row.pack(fill="x", pady=(16, 0))
        ttk.Button(button_row, text="立即刷新", command=self.refresh_now).pack(side="left")
        ttk.Button(button_row, text="退出", command=self.root.destroy).pack(side="right")

    def refresh_now(self) -> None:
        self.status_var.set("正在刷新...")
        thread = threading.Thread(target=self._refresh_worker, daemon=True)
        thread.start()

    def _refresh_worker(self) -> None:
        try:
            snapshot = fetch_snapshot(self.auth_file, self.proxy_server)
            fetched_at = datetime.now()
            state = build_widget_state(snapshot, None, fetched_at)
        except WhamUsageError as exc:
            state = build_widget_state(None, str(exc), None)
        self.root.after(0, lambda: self._apply_state(state))

    def _apply_state(self, state: WidgetState) -> None:
        self.title_var.set(state.title)
        self.subtitle_var.set(state.subtitle)
        self.credits_var.set("\n".join(state.credit_lines))
        self.usage_var.set("\n".join(state.usage_lines))
        self.status_var.set(state.status_text)
        self.status_label.configure(foreground=state.status_color)
        if self._refresh_job is not None:
            self.root.after_cancel(self._refresh_job)
        self._refresh_job = self.root.after(self.refresh_seconds * 1000, self.refresh_now)

    def run(self) -> None:
        self.refresh_now()
        self.root.mainloop()


def render_browser_html(state: WidgetState, refresh_seconds: int) -> str:
    credit_items = "".join(
        f"<li>{html.escape(line)}</li>" for line in state.credit_lines
    )
    usage_items = "".join(
        f"<li>{html.escape(line)}</li>" for line in state.usage_lines
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="{refresh_seconds}">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(state.title)}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f4ecdd;
      --card: #fffaf2;
      --ink: #1f2937;
      --accent: #8a4f08;
      --good: #027a48;
      --bad: #b42318;
      --line: #e7d5ba;
    }}
    body {{
      margin: 0;
      font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      background:
        radial-gradient(circle at top left, #fff4d8 0, transparent 28%),
        linear-gradient(135deg, #efe2c8, #f7f1e5 52%, #eadab5);
      color: var(--ink);
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 24px;
      box-sizing: border-box;
    }}
    .panel {{
      width: min(760px, 100%);
      background: rgba(255, 250, 242, 0.96);
      border: 1px solid var(--line);
      border-radius: 20px;
      box-shadow: 0 20px 60px rgba(73, 45, 5, 0.14);
      padding: 28px;
      backdrop-filter: blur(10px);
    }}
    h1 {{
      margin: 0;
      color: var(--accent);
      font-size: 30px;
    }}
    .subtitle {{
      margin-top: 8px;
      font-size: 15px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 16px;
      margin-top: 24px;
    }}
    .card {{
      background: #fffdf8;
      border: 1px solid #ecdabd;
      border-radius: 16px;
      padding: 18px;
    }}
    h2 {{
      margin: 0 0 10px 0;
      color: var(--accent);
      font-size: 18px;
    }}
    ul {{
      margin: 0;
      padding-left: 18px;
      line-height: 1.8;
      font-size: 15px;
    }}
    .status {{
      margin-top: 18px;
      color: {html.escape(state.status_color)};
      font-size: 14px;
      font-weight: 600;
    }}
    .actions {{
      margin-top: 18px;
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
    }}
    .button {{
      display: inline-block;
      padding: 10px 14px;
      border-radius: 999px;
      background: #8a4f08;
      color: white;
      text-decoration: none;
      font-weight: 600;
    }}
  </style>
</head>
<body>
  <main class="panel">
    <h1>{html.escape(state.title)}</h1>
    <div class="subtitle">{html.escape(state.subtitle)}</div>
    <section class="grid">
      <article class="card">
        <h2>重置卡</h2>
        <ul>{credit_items}</ul>
      </article>
      <article class="card">
        <h2>用量窗口</h2>
        <ul>{usage_items}</ul>
      </article>
    </section>
    <div class="status">{html.escape(state.status_text)}</div>
    <div class="actions">
      <a class="button" href="/">立即刷新</a>
    </div>
  </main>
</body>
</html>
"""


class BrowserDashboard:
    def __init__(
        self,
        auth_file: str,
        refresh_seconds: int,
        proxy_server: str | None,
        no_browser: bool,
    ) -> None:
        self.auth_file = auth_file
        self.refresh_seconds = validate_refresh_seconds(refresh_seconds)
        self.proxy_server = proxy_server
        self.no_browser = no_browser

    def _make_handler(self):
        dashboard = self

        class DashboardHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                if self.path not in {"/", "/index.html"}:
                    self.send_error(404)
                    return
                try:
                    snapshot = fetch_snapshot(dashboard.auth_file, dashboard.proxy_server)
                    state = build_widget_state(snapshot, None, datetime.now())
                except WhamUsageError as exc:
                    state = build_widget_state(None, str(exc), None)
                body = render_browser_html(state, dashboard.refresh_seconds).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args) -> None:
                return

        return DashboardHandler

    def run(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), self._make_handler())
        url = f"http://127.0.0.1:{server.server_port}/"
        print(f"tkinter 不可用，已切换到浏览器看板模式：{url}")
        if not self.no_browser:
            webbrowser.open(url, new=1)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()


def main() -> int:
    args = parse_args()
    refresh_seconds = validate_refresh_seconds(args.refresh_seconds)
    try:
        widget = CodexUsageWidget(
            auth_file=args.auth_file,
            refresh_seconds=refresh_seconds,
            proxy_server=args.proxy_server,
        )
        widget.run()
    except ModuleNotFoundError as exc:
        if exc.name != "tkinter":
            raise
        dashboard = BrowserDashboard(
            auth_file=args.auth_file,
            refresh_seconds=refresh_seconds,
            proxy_server=args.proxy_server,
            no_browser=args.no_browser,
        )
        dashboard.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
