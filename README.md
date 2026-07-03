# codex-wham-usage

用本机 `~/.codex/auth.json` 里的 Codex 凭证，查询：

- rate-limit reset credits
- 5 小时窗口余额与重置时间
- 周窗口余额与重置时间

默认不会打印 `access_token`、`refresh_token`、`cookie` 或完整唯一 ID。

## 命令行运行

```bash
cd /home/admin/code/codex-wham-usage
python3 wham_usage.py
```

如果要指定别的认证文件：

```bash
python3 wham_usage.py --auth-file /path/to/auth.json
```

如果需要显式指定代理：

```bash
python3 wham_usage.py --proxy-server http://127.0.0.1:7890
```

如果不传 `--proxy-server`，程序会自动读取当前命令行环境里的代理变量：

- `HTTPS_PROXY`
- `https_proxy`
- `HTTP_PROXY`
- `http_proxy`
- `ALL_PROXY`
- `all_proxy`

## 桌面小插件

```bash
cd /home/admin/code/codex-wham-usage
python3 desktop_widget.py
```

可选刷新间隔：

```bash
python3 desktop_widget.py --refresh-seconds 300
python3 desktop_widget.py --refresh-seconds 600
python3 desktop_widget.py --proxy-server http://127.0.0.1:7890
python3 desktop_widget.py --no-browser
```

限制是 `300` 到 `600` 秒，也就是每 `5` 到 `10` 分钟刷新一次。

优先使用 Python 自带的 `tkinter` 原生小窗。
如果当前 Python 没有 `tkinter`，程序会自动回退到本地浏览器看板模式，并启动一个只绑定 `127.0.0.1` 的本地页面。
当前界面支持：

- 自动跟随系统明暗模式的浏览器看板
- 原生窗口里的明暗主题切换
- 5 小时和周额度的百分比进度条
- 可直接填写和应用的代理输入框

### Ubuntu

1. 直接运行 `python3 desktop_widget.py`
2. 如果有 `tkinter`，会弹原生小窗
3. 如果没有 `tkinter`，会自动打印本地地址并打开浏览器看板
4. 如果想只打印地址不自动开浏览器，用 `python3 desktop_widget.py --no-browser`
5. 如果终端里已经设置了 `HTTPS_PROXY` 之类的环境变量，小插件会自动复用

### Windows

1. 确认安装的是带 `tkinter` 的 Python
2. 双击运行 `desktop_widget.py`，或者在 PowerShell 里执行 `python desktop_widget.py`
3. 如果某个 Python 环境没有 `tkinter`，也会自动回退到浏览器看板
4. 如果想固定到桌面，可以创建一个指向该命令的快捷方式
5. 如果 PowerShell 里已经设置了 `$env:HTTPS_PROXY` 或 `$env:HTTP_PROXY`，小插件会自动复用

## 打包

### Linux

```bash
cd /home/admin/code/codex-wham-usage
bash scripts/build_linux.sh
```

产物位置：

- `release/linux/codex-usage-widget-linux-x86_64-<timestamp>.tar.gz`

解压后直接运行里面的 `codex-usage-widget`。

### Windows

在 Windows PowerShell 里运行：

```powershell
cd C:\path\to\codex-wham-usage
.\scripts\build_windows.ps1
```

产物位置：

- `release/windows/codex-usage-widget-windows-x86_64-<timestamp>.zip`

解压后运行 `codex-usage-widget.exe`。

### GitHub Actions

推送到 `main` 或手动触发后，工作流 [package.yml](/home/admin/code/codex-wham-usage/.github/workflows/package.yml) 会自动生成：

- Ubuntu `.tar.gz`
- Windows `.zip`

下载路径在 GitHub Actions 的 `Artifacts`。
Windows 本地打包入口就是 `scripts/build_windows.ps1`。

## 测试

```bash
cd /home/admin/code/codex-wham-usage
python3 -m pytest tests evals -q
```
