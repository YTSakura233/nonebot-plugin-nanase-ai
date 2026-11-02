"""NoneBot2 entry point. Runtime I/O starts only in on_startup."""
import re
from types import SimpleNamespace

from nonebot import get_driver, get_plugin_config, on_message
from nonebot.adapters.onebot.v11 import Bot, MessageEvent
from nonebot.matcher import Matcher
from nonebot.plugin import PluginMetadata

from .config import Config
from .core import access, commands, config, db, decision, knowledge, llm, schema, tools, transport
from .core.util import logger, report_exception

__version__ = '0.1.5'
__plugin_meta__ = PluginMetadata(
    name='ナナセ AI', description='人格、好感度、三层记忆、主动闲聊、DeepSeek 与受限工具循环',
    usage='/ai help', type='application', config=Config, supported_adapters={'~onebot.v11'},
)

_ready = False
_command = re.compile(r'^/(ai|summary|help)(?:\s|$)', re.IGNORECASE)


async def startup():
    global _ready
    config.init(get_plugin_config(Config))
    cfg = config.SETTINGS
    if not cfg.soruto_db_user or not cfg.soruto_db_name or not cfg.soruto_deepseek_api_key.get_secret_value():
        logger.error('[soruto] 配置未完成：需要数据库用户/库名及 DeepSeek API Key，当前不接收聊天。')
        return
    try:
        await schema.ensure_schema_async()
        llm.init()
        await knowledge.initialize()
        await tools.registry.initialize()
        _ready = True
        logger.info('[soruto] NoneBot / OneBot V11 插件就绪。')
    except Exception as error:
        report_exception(error, context='startup')
        logger.error('[soruto] 初始化失败，当前不接收聊天；请检查数据库、知识库与技能配置。')
        await shutdown()


async def shutdown():
    global _ready
    _ready = False
    await decision.close()
    await tools.registry.close()
    await llm.close()
    await db.close_async_pool()
    commands._pending.clear()


async def handle_event(bot, event):
    """Return True only when an AI command was consumed."""
    if not _ready or event.user_id == int(bot.self_id):
        return False
    update = transport.from_event(bot, event)
    message = update.effective_message
    text = message.text.strip()
    match = _command.match(text)
    if match is None and any(text.startswith(prefix) for prefix in config.SETTINGS.soruto_ignore_prefixes):
        return False
    if match is not None and match[1].lower() == 'help' and not config.SETTINGS.soruto_enable_help_alias:
        return False
    if match is not None and match[1].lower() == 'help' and len(text.split()) != 1:
        return False
    try:
        if not await access.check_access_async(update):
            return False
        if match is not None:
            name = match[1].lower()
            if name == 'ai':
                await commands.handle_ai_command(message)
            elif name == 'summary':
                await commands.handle_summary_command(message)
            elif len(text.split()) == 1:
                await commands.handle_help_command(message)
            return True
        await decision.handle_ai_update(update, message.get_bot(),
            SimpleNamespace(id=int(bot.self_id), username=''), request_context=message, session_id=message.chat_id)
    except Exception as error:
        report_exception(error)
    return False


def _register():
    driver = get_driver()
    driver.on_startup(startup)
    driver.on_shutdown(shutdown)
    matcher = on_message(priority=99, block=False)

    @matcher.handle()
    async def receive(bot: Bot, event: MessageEvent, matcher: Matcher):
        if await handle_event(bot, event):
            matcher.stop_propagation()

    return matcher


try:
    get_driver()
except ValueError:
    # Allows the offline knowledge CLI and pure business tests to import the package.
    pass
else:
    message_matcher = _register()
