import asyncio
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tomllib
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from nonebot_plugin_soruto_ai.config import Config, MCPServer
from nonebot_plugin_soruto_ai.core import config, tools
from nonebot_plugin_soruto_ai.models import Chat, Message, User


async def test_real_mcp_stdio_sdk_whitelist_and_shutdown():
    pytest.importorskip('mcp')
    root = Path(__file__).resolve().parents[1]
    helper = root/'tests'/'fixtures'/'mcp_server.py'
    args = [str(helper)]
    if (root/'.testdeps').exists():
        args.append(str(root/'.testdeps'))
    original = config.SETTINGS
    config.init(Config(soruto_enable_tools=True, soruto_mcp_servers={
        'notes': MCPServer(transport='stdio', command=sys.executable, args=args,
                           allowed_tools=['read_note'],readonly_tools=['read_note'])}))
    registry = tools.Registry()
    workers = []
    try:
        await registry.initialize()
        assert registry.unavailable == []
        workers = list(registry.workers.values())
        external = [tool for tool in registry.tools.values() if tool.server]
        assert len(external) == 1 and external[0].remote_name == 'read_note'
        msg = Message(Chat('999:private:42','private'),User(42,'test'),1,'test',None)
        result = await registry.execute(external[0].name,{'topic':'hello'},msg)
        assert 'verified:hello' in result
        with pytest.raises(ValueError):
            await registry.execute('write_note',{'topic':'not allowed'},msg)
    finally:
        await registry.close()
        config.init(original)
    assert workers and all(worker.task.done() for worker in workers)


def test_nonebot_can_load_plugin_without_starting_services():
    root = Path(__file__).resolve().parents[1]
    code = """
import site
from pathlib import Path
if Path('.testdeps').exists():
    site.addsitedir('.testdeps')
import nonebot
nonebot.init(_env_file=None)
plugin = nonebot.load_plugin('nonebot_plugin_soruto_ai')
assert plugin is not None
assert plugin.metadata.supported_adapters == {'~onebot.v11'}
assert len(plugin.matcher) == 1
print('OFFLINE_NONEBOT_LOAD_OK')
"""
    result = subprocess.run([sys.executable,'-c',code], cwd=root, capture_output=True, text=True,
                            encoding='utf-8',errors='replace', timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'OFFLINE_NONEBOT_LOAD_OK' in result.stdout
    version = tomllib.loads((root/'pyproject.toml').read_text(encoding='utf-8'))['project']['version']
    installed = root/'.validation'/f'installed-{version}'
    if installed.exists():
        installed_code = code.replace("site.addsitedir('.testdeps')", f"site.addsitedir({str(root/'.testdeps')!r})")
        installed_code = installed_code.replace("Path('.testdeps').exists()", f"Path({str(root/'.testdeps')!r}).exists()")
        installed_code = installed_code.replace('import nonebot',f'import sys\nsys.path.insert(0,{str(installed)!r})\nimport nonebot')
        installed_code += f'\nassert Path(plugin.module.__file__).resolve().is_relative_to(Path({str(installed)!r}))\n'
        installed_code += 'assert plugin.module.decision.SYSTEM_PROMPT_BASE\nassert plugin.module.decision.NG_WORDS\n'
        installed_code += f'assert plugin.module.__version__ == {version!r}\n'
        installed_code += "assert plugin.metadata.name == 'ナナセ AI'\n"
        result = subprocess.run([sys.executable,'-c',installed_code],cwd=root/'.validation',
            capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=20)
        assert result.returncode == 0,result.stdout+result.stderr
        assert 'OFFLINE_NONEBOT_LOAD_OK' in result.stdout
