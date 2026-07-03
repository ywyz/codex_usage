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
```

限制是 `300` 到 `600` 秒，也就是每 `5` 到 `10` 分钟刷新一次。

Ubuntu 和 Windows 都直接用 Python 自带的 `tkinter`，不需要额外安装 GUI 依赖。

### Ubuntu

1. 确认本机能运行 `python3 -m tkinter`
2. 在仓库目录执行 `python3 desktop_widget.py`
3. 如果想做桌面启动器，可以把命令写进 `.desktop` 文件
4. 如果终端里已经设置了 `HTTPS_PROXY` 之类的环境变量，小插件会自动复用

### Windows

1. 确认安装的是带 `tkinter` 的 Python
2. 双击运行 `desktop_widget.py`，或者在 PowerShell 里执行 `python desktop_widget.py`
3. 如果想固定到桌面，可以创建一个指向该命令的快捷方式
4. 如果 PowerShell 里已经设置了 `$env:HTTPS_PROXY` 或 `$env:HTTP_PROXY`，小插件会自动复用

## 测试

```bash
cd /home/admin/code/codex-wham-usage
python3 -m pytest tests evals -q
```
