# codex-wham-usage

用本机 `~/.codex/auth.json` 里的 Codex 凭证，查询：

- rate-limit reset credits
- 5 小时窗口余额与重置时间
- 周窗口余额与重置时间

默认不会打印 `access_token`、`refresh_token`、`cookie` 或完整唯一 ID。

## 运行

```bash
cd /home/admin/code/codex-wham-usage
python3 wham_usage.py
```

如果要指定别的认证文件：

```bash
python3 wham_usage.py --auth-file /path/to/auth.json
```

## 测试

```bash
cd /home/admin/code/codex-wham-usage
python3 -m pytest tests evals -q
```
