# Ubuntu / Conda：已有插件环境的MCP依赖修复

适用报告：Python3.11.0、FastAPI0.115.12、quote0.4.2，另有marshoai1.1.4.1、argot0.2.1、setu-now0.6.6。修订日期：2026-11-02。

先停止机器人，激活原来运行NoneBot的Conda环境。下载本项目0.1.2 wheel并放在当前目录，记录现有版本，再统一安装以下组合：

```bash
python -m pip freeze > before-mcp-fix.txt
python -m pip install \
  ./nonebot_plugin_soruto_ai-0.1.2-py3-none-any.whl \
  'mcp==2.3.0' 'sse-starlette==3.0.2' \
  'fastapi==0.115.12' 'starlette==0.46.2' \
  'httpx==0.27.2' 'aiofiles==24.1.0' 'Pillow==11.1.0'
python -m pip check
```

最后一条预期为No broken requirements found；如果仍列出冲突，保留输出进一步核对，不使用--no-deps忽略。然后验证导入：

```bash
python - <<'PY'
from importlib.metadata import version
from fastapi import FastAPI
from mcp import Client
from mcp.server import MCPServer
for name in ('nonebot-plugin-soruto-ai','mcp','sse-starlette','fastapi','starlette','httpx','aiofiles','Pillow'):
    print(name,version(name))
print('导入成功')
PY
```

依赖检查与导入均成功后，使用原来的命令启动NoneBot。MCP配置继续使用Conda环境的sys.executable绝对路径与知识库脚本绝对路径。若原来是手动复制插件而非安装wheel，应先核对加载目录，避免旧0.1.1源码遮住新安装包。

## 各项为何这样调整

aiofiles24.1.0满足marshoai和argot；Pillow11.1.0同时满足quote的>=11.1,<11.2与setu-now的>=11.0；HTTPX0.27.2满足quote0.4.2，且ナナセ0.1.2已通过该版本回归。0.1.1的HTTPX>=0.28元数据无法共同满足，因此必须同步更新插件。

FastAPI0.115.12要求Starlette>=0.40,<0.47。SSE3.6要求Starlette>=0.49.1，不能只把Starlette单独降级。改用SSE3.0.2并配Starlette0.46.2，同时满足MCP2.3在Python3.11下的要求。MCP使用独立httpx2，与本插件使用的httpx可以共存。

原始元数据：[MCP2.3](https://pypi.org/pypi/mcp/2.3.0/json)、[SSE3.0.2](https://pypi.org/pypi/sse-starlette/3.0.2/json)、[SSE3.6](https://pypi.org/pypi/sse-starlette/3.6.0/json)、[FastAPI0.115.12](https://pypi.org/pypi/fastapi/0.115.12/json)。该组合是定向兼容方案，不要求其他环境使用相同旧版本。
