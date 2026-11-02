import asyncio
import hashlib
import json
from contextlib import AsyncExitStack
from dataclasses import dataclass

import httpx
from jsonschema import Draft202012Validator

from . import config, skills, unfurl
from .util import report_exception


@dataclass
class Tool:
    name: str
    description: str
    schema: dict
    readonly: bool
    server: str | None = None
    remote_name: str | None = None

    def definition(self):
        return {'type': 'function', 'function': {'name': self.name,
            'description': self.description[:1500], 'parameters': self.schema}}


def _schema(properties, required):
    return {'type': 'object', 'properties': properties, 'required': required, 'additionalProperties': False}


class MCPWorker:
    """Keep the SDK client and its AnyIO task groups in their owning task."""
    def __init__(self, cfg):
        self.cfg = cfg
        self.queue = asyncio.Queue(maxsize=32)
        self.ready = asyncio.get_running_loop().create_future()
        self.task = asyncio.create_task(self._run())

    async def _run(self):
        active = None
        try:
            from mcp import Client
            from mcp.client.stdio import StdioServerParameters
            async with AsyncExitStack() as stack:
                cfg = self.cfg
                if cfg.transport == 'stdio':
                    target = StdioServerParameters(command=cfg.command, args=cfg.args, env=cfg.env, cwd=cfg.cwd)
                elif cfg.transport == 'sse':
                    from mcp.client.sse import sse_client
                    target = sse_client(cfg.url, headers=cfg.headers, timeout=10)
                else:
                    from mcp.client.streamable_http import streamable_http_client
                    # SDK v2 uses httpx2 for HTTP transports.
                    import httpx2
                    client = await stack.enter_async_context(httpx2.AsyncClient(headers=cfg.headers, timeout=20))
                    target = streamable_http_client(cfg.url, http_client=client)
                client = await stack.enter_async_context(Client(target, read_timeout_seconds=15, input_required_max_rounds=0))
                available, cursor, seen = [], None, set()
                for _ in range(20):
                    page = await client.list_tools(cursor=cursor)
                    available.extend(page.tools)
                    cursor = page.next_cursor
                    if cursor is None:
                        break
                    if cursor in seen:
                        raise ValueError('MCP pagination cursor repeated')
                    seen.add(cursor)
                else:
                    raise ValueError('MCP tool listing exceeds page limit')
                self.ready.set_result(available)
                while True:
                    active = await self.queue.get()
                    if active is None:
                        break
                    future, name, arguments = active
                    if future.cancelled():
                        active = None
                        continue
                    try:
                        result = await client.call_tool(name, arguments,
                            read_timeout_seconds=config.SETTINGS.soruto_tool_timeout_seconds)
                        data = result.model_dump(by_alias=True, exclude_none=True)
                        blocks = [item.get('text', '') for item in data.get('content', []) if item.get('type') == 'text']
                        if data.get('structuredContent') is not None:
                            blocks.append(json.dumps(data['structuredContent'], ensure_ascii=False))
                        if data.get('isError'):
                            raise RuntimeError('MCP tool returned an error')
                        if not future.done():
                            future.set_result('\n'.join(blocks)[:12000] or '工具未返回文本内容。')
                    except Exception as error:
                        if not future.done():
                            future.set_exception(error)
                    finally:
                        active = None
        except BaseException as error:
            if not self.ready.done():
                self.ready.set_exception(error)
            if active is not None and not active[0].done():
                active[0].set_exception(RuntimeError('MCP connection closed during tool execution'))
        finally:
            while not self.queue.empty():
                item = self.queue.get_nowait()
                if item is not None and not item[0].done():
                    item[0].set_exception(RuntimeError('MCP connection closed'))

    async def call(self, name, arguments):
        if self.task.done():
            raise RuntimeError('MCP server is disconnected')
        future = asyncio.get_running_loop().create_future()
        self.queue.put_nowait((future, name, arguments))
        return await future

    async def close(self):
        self.task.cancel()
        await asyncio.gather(self.task, return_exceptions=True)


class Registry:
    def __init__(self):
        self.tools = {}
        self.workers = {}
        self.unavailable = []
        self.client = None

    async def initialize(self):
        self.unavailable = []
        self.client = httpx.AsyncClient(timeout=15)
        skills.initialize()
        self.tools = {
            'web_search': Tool('web_search', '搜索公开网页，返回真实标题、URL与内容摘要。',
                _schema({'query': {'type':'string','minLength':1,'maxLength':128}}, ['query']), True),
            'web_fetch': Tool('web_fetch', '读取一个公开网页，返回来源URL与正文。',
                _schema({'url': {'type':'string','maxLength':2000}}, ['url']), True),
        }
        if skills.prompt():
            self.tools['skill_read'] = Tool('skill_read', '读取已启用技能的SKILL.md或目录内引用文件，不执行脚本。',
                _schema({'name': {'type':'string'}, 'path': {'type':'string'}}, ['name']), True)
        if not config.ENABLE_TOOLS:
            return
        for name, cfg in config.SETTINGS.soruto_mcp_servers.items():
            worker = MCPWorker(cfg)
            self.workers[name] = worker
            try:
                available = await asyncio.wait_for(asyncio.shield(worker.ready), 15)
                loaded = {}
                for remote in available:
                    if remote.name not in cfg.allowed_tools:
                        continue
                    schema = remote.input_schema
                    Draft202012Validator.check_schema(schema)
                    alias = 'mcp_' + hashlib.sha256(f'{name}:{remote.name}'.encode()).hexdigest()[:20]
                    loaded[alias] = Tool(alias, f'[{name}/{remote.name}] {remote.description or ""}',
                        schema, remote.name in cfg.readonly_tools, name, remote.name)
                self.tools.update(loaded)
            except Exception as error:
                report_exception(error)
                self.unavailable.append(name)
                await worker.close()
                # Retrieve a late handshake failure so no Future exception is left unobserved.
                if worker.ready.done() and not worker.ready.cancelled():
                    worker.ready.exception()

    def permitted(self, tool, message, casual=False):
        if casual and (not tool.readonly or tool.name not in config.CASUAL_TOOL_NAMES):
            # MCP casual names are configured as server/remote_name, not opaque aliases.
            if not (tool.server and tool.readonly and f'{tool.server}/{tool.remote_name}' in config.CASUAL_TOOL_NAMES):
                return False
        if tool.server is not None:
            server = config.SETTINGS.soruto_mcp_servers[tool.server]
            if server.allowed_users and message.from_user.id not in server.allowed_users:
                return False
            if server.allowed_groups:
                if message.chat.type != 'group' or int(message.chat_id.rsplit(':',1)[1]) not in server.allowed_groups:
                    return False
        return True

    def available(self, message, casual=False):
        return [tool.definition() for tool in self.tools.values() if self.permitted(tool, message, casual)]

    async def execute(self, name, arguments, message, casual=False):
        tool = self.tools.get(name)
        if tool is None or not self.permitted(tool, message, casual):
            raise ValueError('tool is not permitted for this turn')
        Draft202012Validator(tool.schema).validate(arguments)
        if tool.server:
            return await self.workers[tool.server].call(tool.remote_name, arguments)
        if name == 'skill_read':
            return await asyncio.to_thread(skills.read, **arguments)
        endpoint = 'search' if name == 'web_search' else 'fetch'
        payload = dict(arguments)
        if endpoint == 'search':
            payload.update(count=5, need_content=True)
        elif not await asyncio.to_thread(unfurl._is_public_http_url, payload['url']):
            raise ValueError('web URL is not public HTTP(S)')
        response = await self.client.post(f'https://api.deepseek.com/v1/tools/{endpoint}', json=payload,
            headers={'Authorization': 'Bearer ' + config.SETTINGS.soruto_deepseek_api_key.get_secret_value()})
        response.raise_for_status()
        data = response.json()
        if endpoint == 'search':
            data = [{'title': row.get('title'), 'url': row.get('url'),
                     'text': str(row.get('content') or row.get('summary') or row.get('snippet') or '')[:1800]}
                    for row in data.get('results', [])[:5]]
        else:
            data = {'url': arguments['url'], 'title':data.get('title'), 'content':str(data.get('content') or '')[:10000]}
        return json.dumps(data, ensure_ascii=False)[:12000]

    async def close(self):
        await asyncio.gather(*(worker.close() for worker in self.workers.values()), return_exceptions=True)
        self.workers.clear()
        if self.client is not None:
            await self.client.aclose()
        self.tools.clear()


registry = Registry()
