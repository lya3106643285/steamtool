# Steam 本地数据工具

Python 3.11+ / WSL。依据仓库任务书，按五个阶段实现，只读访问 Steam。

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

配置模板为 `.env.example`；需要账号功能时自行复制为 `.env` 并在本机填写。
真实凭据、运行结果与运行日志均不进入 Git。开发进度和验证边界见 `task/IMPLEMENTATION.md`。
