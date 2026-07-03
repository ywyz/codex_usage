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
from urllib.parse import parse_qs, urlparse

from wham_usage import UsageSnapshot, WhamUsageError, fetch_snapshot

if TYPE_CHECKING:
    import tkinter as tk
    from tkinter import ttk


DEFAULT_REFRESH_SECONDS = 300
MAX_REFRESH_SECONDS = 600
MIN_REFRESH_SECONDS = 300


@dataclass(frozen=True)
class CreditDisplay:
    index: int
    granted_at: str
    expires_at: str


@dataclass(frozen=True)
class WindowDisplay:
    name: str
    remaining_percent: int
    used_percent: int
    reset_at: str


@dataclass(frozen=True)
class WidgetState:
    title: str
    subtitle: str
    credits: list[CreditDisplay]
    windows: list[WindowDisplay]
    proxy_server: str
    status_text: str
    status_color: str
    error_message: str | None


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
    proxy_server: str | None = None,
) -> WidgetState:
    if error_message:
        return WidgetState(
            title="Codex 用量看板",
            subtitle="数据刷新失败",
            credits=[],
            windows=[],
            proxy_server=proxy_server or "",
            status_text=error_message,
            status_color="#ff7b72",
            error_message=error_message,
        )

    assert snapshot is not None
    credits = [
        CreditDisplay(
            index=index,
            granted_at=credit.granted_at,
            expires_at=credit.expires_at,
        )
        for index, credit in enumerate(snapshot.credits, start=1)
    ]
    windows = [
        WindowDisplay(
            name=window.name,
            remaining_percent=window.remaining_percent,
            used_percent=window.used_percent,
            reset_at=window.reset_at,
        )
        for window in snapshot.windows
    ]
    stamp = fetched_at.strftime("%Y-%m-%d %H:%M:%S") if fetched_at else "未知"
    return WidgetState(
        title="Codex 用量看板",
        subtitle="重置卡、5 小时余量、周余量",
        credits=credits,
        windows=windows,
        proxy_server=proxy_server or "",
        status_text=f"最近刷新：{stamp}",
        status_color="#4ade80",
        error_message=None,
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
        self.proxy_server = proxy_server or ""
        self.root = tk.Tk()
        self.root.title("Codex 用量看板")
        self.root.geometry("560x680")
        self.root.minsize(520, 620)
        self._theme = "dark"

        self.title_var = tk.StringVar(value="Codex 用量看板")
        self.subtitle_var = tk.StringVar(value="准备加载...")
        self.status_var = tk.StringVar(value="正在初始化")
        self.proxy_var = tk.StringVar(value=self.proxy_server)

        self.status_label: ttk.Label
        self.proxy_entry: ttk.Entry
        self.credit_frame: ttk.Frame
        self.window_frame: ttk.Frame
        self.window_progressbars: list[tuple[WindowDisplay, ttk.Progressbar, ttk.Label]] = []
        self._refresh_job: str | None = None
        self._build_ui()

    def _apply_theme(self) -> None:
        ttk = self._ttk
        palette = {
            "dark": {
                "bg": "#0f172a",
                "card": "#111827",
                "card_alt": "#172033",
                "line": "#334155",
                "text": "#e5eefc",
                "muted": "#9fb0ca",
                "accent": "#f59e0b",
                "good": "#4ade80",
                "bad": "#f87171",
                "track": "#1f2937",
                "bar": "#22c55e",
                "entry": "#0b1220",
            },
            "light": {
                "bg": "#f3efe7",
                "card": "#fffaf2",
                "card_alt": "#fffdf8",
                "line": "#e5d7bf",
                "text": "#172033",
                "muted": "#5b6578",
                "accent": "#9a5b06",
                "good": "#15803d",
                "bad": "#b91c1c",
                "track": "#e2e8f0",
                "bar": "#16a34a",
                "entry": "#ffffff",
            },
        }[self._theme]
        self.palette = palette
        self.root.configure(bg=palette["bg"])
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except self._tk.TclError:
            pass
        style.configure("Shell.TFrame", background=palette["bg"])
        style.configure("Card.TFrame", background=palette["card"])
        style.configure("CardAlt.TFrame", background=palette["card_alt"])
        style.configure(
            "Title.TLabel",
            background=palette["bg"],
            foreground=palette["text"],
        )
        style.configure(
            "Subtitle.TLabel",
            background=palette["bg"],
            foreground=palette["muted"],
        )
        style.configure(
            "CardTitle.TLabel",
            background=palette["card"],
            foreground=palette["accent"],
        )
        style.configure(
            "Body.TLabel",
            background=palette["card"],
            foreground=palette["text"],
        )
        style.configure(
            "Muted.TLabel",
            background=palette["card"],
            foreground=palette["muted"],
        )
        style.configure(
            "Status.TLabel",
            background=palette["bg"],
            foreground=palette["good"],
        )
        style.configure(
            "Accent.TButton",
            background=palette["accent"],
            foreground="#ffffff",
            borderwidth=0,
            focusthickness=3,
            focuscolor=palette["accent"],
        )
        style.map(
            "Accent.TButton",
            background=[("active", palette["bar"])],
        )
        style.configure(
            "Toggle.TButton",
            background=palette["card"],
            foreground=palette["text"],
            bordercolor=palette["line"],
        )
        style.configure(
            "Proxy.TEntry",
            fieldbackground=palette["entry"],
            foreground=palette["text"],
            insertcolor=palette["text"],
            bordercolor=palette["line"],
        )
        style.configure(
            "Usage.Horizontal.TProgressbar",
            troughcolor=palette["track"],
            background=palette["bar"],
            bordercolor=palette["track"],
            lightcolor=palette["bar"],
            darkcolor=palette["bar"],
        )

    def _build_ui(self) -> None:
        ttk = self._ttk
        self._apply_theme()

        shell = ttk.Frame(self.root, padding=18, style="Shell.TFrame")
        shell.pack(fill="both", expand=True)

        header = ttk.Frame(shell, style="Shell.TFrame")
        header.pack(fill="x")
        ttk.Label(
            header,
            textvariable=self.title_var,
            font=("Segoe UI", 22, "bold"),
            style="Title.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            header,
            textvariable=self.subtitle_var,
            font=("Segoe UI", 10),
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(4, 12))

        top_actions = ttk.Frame(shell, style="Shell.TFrame")
        top_actions.pack(fill="x", pady=(0, 14))
        ttk.Button(
            top_actions,
            text="切换明暗",
            command=self.toggle_theme,
            style="Toggle.TButton",
        ).pack(side="left")
        ttk.Button(
            top_actions,
            text="立即刷新",
            command=self.refresh_now,
            style="Accent.TButton",
        ).pack(side="right")

        proxy_card = ttk.Frame(shell, padding=16, style="Card.TFrame")
        proxy_card.pack(fill="x", pady=(0, 14))
        ttk.Label(
            proxy_card,
            text="代理设置",
            font=("Segoe UI", 12, "bold"),
            style="CardTitle.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            proxy_card,
            text="支持 http://127.0.0.1:7890，留空则继续使用命令行环境变量代理。",
            font=("Segoe UI", 9),
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(4, 10))
        entry_row = ttk.Frame(proxy_card, style="Card.TFrame")
        entry_row.pack(fill="x")
        self.proxy_entry = ttk.Entry(
            entry_row,
            textvariable=self.proxy_var,
            style="Proxy.TEntry",
            font=("Consolas", 11),
        )
        self.proxy_entry.pack(side="left", fill="x", expand=True)
        ttk.Button(
            entry_row,
            text="应用代理",
            command=self.apply_proxy_and_refresh,
            style="Accent.TButton",
        ).pack(side="left", padx=(10, 0))

        usage_card = ttk.Frame(shell, padding=16, style="Card.TFrame")
        usage_card.pack(fill="x", pady=(0, 14))
        ttk.Label(
            usage_card,
            text="用量窗口",
            font=("Segoe UI", 12, "bold"),
            style="CardTitle.TLabel",
        ).pack(anchor="w")
        self.window_frame = ttk.Frame(usage_card, style="Card.TFrame")
        self.window_frame.pack(fill="x", pady=(8, 0))

        credit_card = ttk.Frame(shell, padding=16, style="Card.TFrame")
        credit_card.pack(fill="both", expand=True, pady=(0, 14))
        ttk.Label(
            credit_card,
            text="重置卡",
            font=("Segoe UI", 12, "bold"),
            style="CardTitle.TLabel",
        ).pack(anchor="w")
        self.credit_frame = ttk.Frame(credit_card, style="Card.TFrame")
        self.credit_frame.pack(fill="both", expand=True, pady=(8, 0))

        footer = ttk.Frame(shell, style="Shell.TFrame")
        footer.pack(fill="x")
        self.status_label = ttk.Label(
            footer,
            textvariable=self.status_var,
            font=("Segoe UI", 10),
            style="Status.TLabel",
        )
        self.status_label.pack(side="left")
        ttk.Button(
            footer,
            text="退出",
            command=self.root.destroy,
            style="Toggle.TButton",
        ).pack(side="right")

    def toggle_theme(self) -> None:
        self._theme = "light" if self._theme == "dark" else "dark"
        self._apply_theme()
        self._repaint_cards()

    def apply_proxy_and_refresh(self) -> None:
        self.proxy_server = self.proxy_var.get().strip()
        self.refresh_now()

    def _clear_frame(self, frame) -> None:
        for child in frame.winfo_children():
            child.destroy()

    def _repaint_cards(self) -> None:
        # Force existing dynamic sections to pick up the new palette.
        current_state = getattr(self, "_last_state", None)
        if current_state is not None:
            self._apply_state(current_state)

    def refresh_now(self) -> None:
        self.status_var.set("正在刷新...")
        thread = threading.Thread(target=self._refresh_worker, daemon=True)
        thread.start()

    def _refresh_worker(self) -> None:
        try:
            snapshot = fetch_snapshot(self.auth_file, self.proxy_server or None)
            fetched_at = datetime.now()
            state = build_widget_state(snapshot, None, fetched_at, self.proxy_server)
        except WhamUsageError as exc:
            state = build_widget_state(None, str(exc), None, self.proxy_server)
        self.root.after(0, lambda: self._apply_state(state))

    def _render_windows(self, state: WidgetState) -> None:
        ttk = self._ttk
        self._clear_frame(self.window_frame)
        if not state.windows:
            ttk.Label(
                self.window_frame,
                text="暂无可展示的用量窗口数据",
                style="Muted.TLabel",
                font=("Segoe UI", 10),
            ).pack(anchor="w")
            return
        for window in state.windows:
            card = ttk.Frame(self.window_frame, padding=12, style="CardAlt.TFrame")
            card.pack(fill="x", pady=(0, 10))
            top = ttk.Frame(card, style="CardAlt.TFrame")
            top.pack(fill="x")
            ttk.Label(
                top,
                text=window.name,
                font=("Segoe UI", 11, "bold"),
                style="Body.TLabel",
            ).pack(side="left")
            ttk.Label(
                top,
                text=f"余量 {window.remaining_percent}%",
                font=("Segoe UI", 11, "bold"),
                style="Body.TLabel",
            ).pack(side="right")
            bar = ttk.Progressbar(
                card,
                style="Usage.Horizontal.TProgressbar",
                maximum=100,
                value=window.remaining_percent,
            )
            bar.pack(fill="x", pady=(10, 8))
            ttk.Label(
                card,
                text=f"已用 {window.used_percent}%  |  重置时间 {window.reset_at}",
                font=("Segoe UI", 9),
                style="Muted.TLabel",
            ).pack(anchor="w")

    def _render_credits(self, state: WidgetState) -> None:
        ttk = self._ttk
        self._clear_frame(self.credit_frame)
        if state.error_message:
            ttk.Label(
                self.credit_frame,
                text="无法读取重置卡信息",
                font=("Segoe UI", 11, "bold"),
                style="Body.TLabel",
            ).pack(anchor="w")
            ttk.Label(
                self.credit_frame,
                text="请检查本机 Codex 凭证、代理或网络连接",
                font=("Segoe UI", 9),
                style="Muted.TLabel",
            ).pack(anchor="w", pady=(6, 0))
            return
        if not state.credits:
            ttk.Label(
                self.credit_frame,
                text="当前没有可展示的重置卡",
                font=("Segoe UI", 10),
                style="Muted.TLabel",
            ).pack(anchor="w")
            return
        for credit in state.credits:
            card = ttk.Frame(self.credit_frame, padding=12, style="CardAlt.TFrame")
            card.pack(fill="x", pady=(0, 10))
            ttk.Label(
                card,
                text=f"第 {credit.index} 张重置卡",
                font=("Segoe UI", 11, "bold"),
                style="Body.TLabel",
            ).pack(anchor="w")
            ttk.Label(
                card,
                text=f"发放时间：{credit.granted_at}",
                font=("Consolas", 10),
                style="Muted.TLabel",
            ).pack(anchor="w", pady=(6, 2))
            ttk.Label(
                card,
                text=f"过期时间：{credit.expires_at}",
                font=("Consolas", 10),
                style="Muted.TLabel",
            ).pack(anchor="w")

    def _apply_state(self, state: WidgetState) -> None:
        self._last_state = state
        self.title_var.set(state.title)
        self.subtitle_var.set(state.subtitle)
        self.proxy_var.set(state.proxy_server)
        self.status_var.set(state.status_text)
        self.status_label.configure(foreground=state.status_color)
        self._render_windows(state)
        self._render_credits(state)
        if self._refresh_job is not None:
            self.root.after_cancel(self._refresh_job)
        self._refresh_job = self.root.after(self.refresh_seconds * 1000, self.refresh_now)

    def run(self) -> None:
        self.refresh_now()
        self.root.mainloop()


def render_browser_html(state: WidgetState, refresh_seconds: int) -> str:
    credit_items = "".join(
        (
            "<article class='credit-card'>"
            f"<h3>第 {credit.index} 张重置卡</h3>"
            f"<p>发放时间：{html.escape(credit.granted_at)}</p>"
            f"<p>过期时间：{html.escape(credit.expires_at)}</p>"
            "</article>"
        )
        for credit in state.credits
    )
    if not credit_items:
        credit_items = "<p class='empty'>当前没有可展示的重置卡</p>"

    usage_items = "".join(
        (
            "<article class='usage-card'>"
            f"<div class='usage-head'><h3>{html.escape(window.name)}</h3><span>{window.remaining_percent}%</span></div>"
            f"<div class='progress'><div class='progress-fill' style='width:{window.remaining_percent}%'></div></div>"
            f"<p>已用 {window.used_percent}%</p>"
            f"<p>重置时间：{html.escape(window.reset_at)}</p>"
            "</article>"
        )
        for window in state.windows
    )
    if not usage_items:
        usage_items = "<p class='empty'>暂无可展示的用量窗口数据</p>"

    error_block = (
        f"<div class='error'>{html.escape(state.error_message)}</div>"
        if state.error_message
        else ""
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
      color-scheme: light dark;
      --bg: #f3efe7;
      --card: rgba(255, 250, 242, 0.96);
      --card-alt: #fffdf8;
      --ink: #172033;
      --muted: #5b6578;
      --accent: #a16207;
      --line: #e5d7bf;
      --good: #15803d;
      --bad: #b91c1c;
      --track: #e2e8f0;
      --fill: linear-gradient(90deg, #16a34a, #4ade80);
      --input: #ffffff;
      --shadow: 0 20px 60px rgba(73, 45, 5, 0.14);
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --bg: #0f172a;
        --card: rgba(17, 24, 39, 0.96);
        --card-alt: #172033;
        --ink: #e5eefc;
        --muted: #9fb0ca;
        --accent: #f59e0b;
        --line: #334155;
        --good: #4ade80;
        --bad: #f87171;
        --track: #1f2937;
        --fill: linear-gradient(90deg, #22c55e, #86efac);
        --input: #0b1220;
        --shadow: 0 20px 60px rgba(0, 0, 0, 0.35);
      }}
    }}
    body {{
      margin: 0;
      font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      background:
        radial-gradient(circle at top left, rgba(245, 158, 11, 0.18) 0, transparent 24%),
        linear-gradient(135deg, var(--bg), color-mix(in srgb, var(--bg) 75%, #101826));
      color: var(--ink);
      min-height: 100vh;
      padding: 24px;
      box-sizing: border-box;
    }}
    .panel {{
      width: min(960px, 100%);
      margin: 0 auto;
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 24px;
      box-shadow: var(--shadow);
      padding: 28px;
      backdrop-filter: blur(14px);
    }}
    .header {{
      display: flex;
      justify-content: space-between;
      gap: 18px;
      align-items: flex-start;
      flex-wrap: wrap;
    }}
    h1 {{
      margin: 0;
      font-size: 32px;
      color: var(--accent);
    }}
    .subtitle {{
      margin-top: 8px;
      color: var(--muted);
      font-size: 15px;
    }}
    .status {{
      margin-top: 12px;
      color: {html.escape(state.status_color)};
      font-size: 14px;
      font-weight: 700;
    }}
    .toolbar {{
      display: flex;
      gap: 10px;
      align-items: center;
      flex-wrap: wrap;
    }}
    .button {{
      display: inline-block;
      padding: 10px 14px;
      border-radius: 999px;
      background: var(--accent);
      color: white;
      text-decoration: none;
      font-weight: 700;
      border: none;
      cursor: pointer;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 16px;
      margin-top: 24px;
    }}
    .card {{
      background: var(--card-alt);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 18px;
    }}
    h2 {{
      margin: 0 0 14px 0;
      font-size: 18px;
      color: var(--accent);
    }}
    .usage-card, .credit-card {{
      padding: 14px;
      border-radius: 14px;
      background: color-mix(in srgb, var(--card-alt) 82%, transparent);
      border: 1px solid var(--line);
      margin-bottom: 12px;
    }}
    .usage-card:last-child, .credit-card:last-child {{
      margin-bottom: 0;
    }}
    .usage-head {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
    }}
    h3 {{
      margin: 0;
      font-size: 16px;
    }}
    .usage-head span {{
      font-weight: 800;
      color: var(--good);
    }}
    .progress {{
      height: 14px;
      border-radius: 999px;
      background: var(--track);
      overflow: hidden;
      margin: 12px 0 10px;
    }}
    .progress-fill {{
      height: 100%;
      border-radius: 999px;
      background: var(--fill);
    }}
    p {{
      margin: 6px 0 0;
      color: var(--muted);
      font-size: 14px;
    }}
    .proxy-form {{
      display: flex;
      gap: 10px;
      align-items: center;
      flex-wrap: wrap;
      margin-top: 18px;
      padding: 16px;
      border-radius: 18px;
      background: var(--card-alt);
      border: 1px solid var(--line);
    }}
    .proxy-form label {{
      font-weight: 700;
      min-width: 72px;
    }}
    .proxy-form input {{
      flex: 1;
      min-width: 260px;
      padding: 11px 14px;
      border-radius: 12px;
      border: 1px solid var(--line);
      background: var(--input);
      color: var(--ink);
      font-size: 14px;
    }}
    .helper {{
      width: 100%;
      color: var(--muted);
      font-size: 13px;
    }}
    .empty {{
      color: var(--muted);
      margin: 0;
    }}
    .error {{
      margin-top: 14px;
      padding: 12px 14px;
      border-radius: 14px;
      background: color-mix(in srgb, var(--bad) 14%, transparent);
      color: var(--bad);
      font-weight: 700;
    }}
  </style>
</head>
<body>
  <main class="panel">
    <div class="header">
      <div>
        <h1>{html.escape(state.title)}</h1>
        <div class="subtitle">{html.escape(state.subtitle)}</div>
        <div class="status">{html.escape(state.status_text)}</div>
        {error_block}
      </div>
      <div class="toolbar">
        <a class="button" href="/">立即刷新</a>
      </div>
    </div>
    <form class="proxy-form" method="get" action="/">
      <label for="proxy">代理</label>
      <input id="proxy" name="proxy" value="{html.escape(state.proxy_server)}" placeholder="http://127.0.0.1:7890">
      <button class="button" type="submit">应用代理</button>
      <div class="helper">这里填写代理地址。留空则继续使用命令行环境变量里的代理。</div>
    </form>
    <section class="grid">
      <article class="card">
        <h2>用量窗口</h2>
        {usage_items}
      </article>
      <article class="card">
        <h2>重置卡</h2>
        {credit_items}
      </article>
    </section>
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
        self.proxy_server = proxy_server or ""
        self.no_browser = no_browser

    def _make_handler(self):
        dashboard = self

        class DashboardHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                if urlparse(self.path).path not in {"/", "/index.html"}:
                    self.send_error(404)
                    return
                params = parse_qs(urlparse(self.path).query)
                if "proxy" in params:
                    dashboard.proxy_server = params.get("proxy", [""])[0].strip()
                try:
                    snapshot = fetch_snapshot(
                        dashboard.auth_file,
                        dashboard.proxy_server or None,
                    )
                    state = build_widget_state(
                        snapshot,
                        None,
                        datetime.now(),
                        dashboard.proxy_server,
                    )
                except WhamUsageError as exc:
                    state = build_widget_state(
                        None,
                        str(exc),
                        None,
                        dashboard.proxy_server,
                    )
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
