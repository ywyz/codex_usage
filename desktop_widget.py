#!/usr/bin/env python3
"""Desktop widget for Codex WHAM usage on Ubuntu and Windows."""

from __future__ import annotations

import argparse
import threading
import tkinter as tk
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tkinter import ttk

from wham_usage import UsageSnapshot, WhamUsageError, fetch_snapshot


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
            usage_lines=["请检查本机 Codex 凭证或网络连接"],
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


class CodexUsageWidget:
    def __init__(self, auth_file: str, refresh_seconds: int) -> None:
        self.auth_file = auth_file
        self.refresh_seconds = validate_refresh_seconds(refresh_seconds)
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
        self._build_ui()

    def _build_ui(self) -> None:
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
            snapshot = fetch_snapshot(self.auth_file)
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
        self.root.after(self.refresh_seconds * 1000, self.refresh_now)

    def run(self) -> None:
        self.refresh_now()
        self.root.mainloop()


def main() -> int:
    args = parse_args()
    widget = CodexUsageWidget(
        auth_file=args.auth_file,
        refresh_seconds=validate_refresh_seconds(args.refresh_seconds),
    )
    widget.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
