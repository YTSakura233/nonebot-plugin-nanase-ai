from unittest.mock import patch

import httpx
import pytest
from pymysql.err import OperationalError

from nonebot_plugin_soruto_ai.core import util


def capture(error, **kwargs):
    with patch.object(util.logger,'warning') as warning:
        util.report_exception(error,**kwargs)
    fmt,*values=warning.call_args.args
    return fmt % tuple(values)


def test_http_status_comes_from_response_without_leaking_request_or_body():
    request=httpx.Request('POST','https://name:password@api.deepseek.com/chat/completions?api_key=secret',
                          headers={'Authorization':'Bearer secret'},json={'messages':['private-chat']})
    response=httpx.Response(400,request=request,json={'error':'private-chat secret'})
    error=httpx.HTTPStatusError('private-chat secret',request=request,response=response)
    text=capture(error,context='model_summary')
    assert 'HTTP 400' in text and 'api=DeepSeek/chat' in text and 'context=model_summary' in text
    for value in ('secret','password','private-chat','https://','Authorization'):
        assert value not in text


def test_onebot_request_is_labeled_without_logging_address_or_token():
    request=httpx.Request('POST','http://127.0.0.1:1234/private-prefix/send_msg?access_token=secret')
    response=httpx.Response(403,request=request)
    error=httpx.HTTPStatusError('secret',request=request,response=response)
    text=capture(error)
    assert 'HTTP 403' in text and 'api=OneBot/send_msg' in text
    assert '127.0.0.1' not in text and 'secret' not in text and 'private-prefix' not in text


def test_unknown_endpoint_is_not_printed():
    request=httpx.Request('GET','https://private.example/token-secret')
    response=httpx.Response(500,request=request)
    text=capture(httpx.HTTPStatusError('secret',request=request,response=response))
    assert 'HTTP 500' in text and 'api=HTTP' in text
    assert 'private.example' not in text and 'token-secret' not in text


def test_mysql_code_is_logged_without_credentials_or_sql():
    text=capture(OperationalError(1049,"secret-user secret-password private-db"),context='startup')
    assert 'MySQL 1049' in text and 'context=startup' in text
    assert 'secret' not in text and 'private-db' not in text


def test_incomplete_http_exception_metadata_does_not_crash_logging():
    request=httpx.Request('GET','https://example.com')
    response=httpx.Response(429)  # no associated request
    text=capture(httpx.HTTPStatusError('secret',request=request,response=response))
    assert 'HTTP 429' in text and 'secret' not in text


def test_unknown_context_and_exception_text_are_not_logged():
    text=capture(RuntimeError('private-chat secret'),context='private-chat secret')
    assert 'RuntimeError' in text and 'private-chat' not in text and 'secret' not in text


@pytest.mark.asyncio
async def test_plugin_source_location_is_available_without_locals():
    with patch.object(util.logger,'warning') as warning:
        try:
            await util.safe_reply_text(object(),'private-chat secret')
        except AttributeError as error:
            util.report_exception(error)
    fmt,*values=warning.call_args.args
    text=fmt % tuple(values)
    assert 'at=util.py:' in text and 'safe_reply_text' in text
    assert 'private-chat' not in text and 'secret' not in text
