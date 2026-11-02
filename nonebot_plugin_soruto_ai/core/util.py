from pathlib import Path

from nonebot import logger as _logger
from pymysql.err import MySQLError


class _Logger:
    def info(self, message, *args):
        _logger.info(message % args if args else message)

    def warning(self, message, *args):
        _logger.warning(message % args if args else message)

    def error(self, message, *args):
        _logger.error(message % args if args else message)


logger = _Logger()


def is_transient_error(error):
    import httpx
    return isinstance(error, (TimeoutError, httpx.TransportError))


_LOG_CONTEXTS = {'model_simple', 'model_complex', 'model_decision', 'model_summary',
                 'model_vision', 'model_unknown', 'agent_tool', 'startup'}
_PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def report_exception(error, *, context=None):
    """Log bounded metadata only: never exception text, URLs, bodies or locals."""
    details = [type(error).__name__]
    if isinstance(context, str) and context in _LOG_CONTEXTS:
        details.append(f'context={context}')
    try:
        response = getattr(error, 'response', None)
        status = getattr(response, 'status_code', None)
        if type(status) is not int:
            status = getattr(error, 'status_code', None)
        if type(status) is int and 100 <= status <= 599:
            details.append(f'HTTP {status}')
        request = getattr(response, 'request', None) if response is not None else None
        if request is not None:
            url = request.url
            if url.host == 'api.deepseek.com':
                names = {'/chat/completions':'DeepSeek/chat', '/v1/chat/completions':'DeepSeek/chat',
                         '/v1/tools/search':'DeepSeek/search', '/v1/tools/fetch':'DeepSeek/fetch'}
                label = names.get(url.path, 'DeepSeek')
            elif url.path.rsplit('/',1)[-1] in {'send_msg','send_group_msg','send_private_msg','get_image','get_group_member_info'}:
                label = 'OneBot/' + url.path.rsplit('/',1)[-1]
            else:
                label = 'HTTP'
            details.append(f'api={label}')
        if isinstance(error, MySQLError) and error.args and type(error.args[0]) is int:
            details.append(f'MySQL {error.args[0]}')
        origin = None
        trace = error.__traceback__
        while trace is not None:
            filename = Path(trace.tb_frame.f_code.co_filename).resolve()
            if filename.is_relative_to(_PACKAGE_ROOT):
                origin = f'{filename.name}:{trace.tb_lineno}:{trace.tb_frame.f_code.co_name}'
            trace = trace.tb_next
        if origin:
            details.append(f'at={origin}')
    except Exception:
        # Incomplete third-party exception metadata must not mask the original error.
        pass
    logger.warning('[soruto] %s', ' '.join(details))


async def safe_reply_text(message, text, **kwargs):
    if message is None:
        return None
    from . import config, decision
    result = None
    for index, part in enumerate(decision._split_reply(text, config.SETTINGS.soruto_reply_units)):
        if index == 0:
            result = await message.reply_text(part)
        else:
            await message.get_bot().send_message(message.chat_id, part)
    return result
