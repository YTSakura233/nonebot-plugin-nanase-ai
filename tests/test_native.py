import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
from nonebot.adapters.onebot.v11 import GroupMessageEvent, PrivateMessageEvent, Message as OBMessage

import nonebot_plugin_soruto_ai as plugin
from nonebot_plugin_soruto_ai.config import Config, MCPServer
from nonebot_plugin_soruto_ai.core import access, config, decision, knowledge, llm, skills, tools, transport
from nonebot_plugin_soruto_ai.models import Chat, Message, Update, User


@pytest.fixture
def settings():
    original = config.SETTINGS
    config.init(Config(soruto_allowed_groups={123}, soruto_deepseek_api_key='test-key'))
    yield config.SETTINGS
    config.init(original)


def message(private=False):
    return Message(Chat('999:private:42' if private else '999:group:123', 'private' if private else 'group'),
                   User(42, '群友'), 7, '你好', Mock())


def event(group=True, text='你好', sender_id=42):
    data = dict(time=int(datetime.now(timezone.utc).timestamp())+1, self_id=999, post_type='message',
        sub_type='normal' if group else 'friend', user_id=sender_id, message_id=7, raw_message=text,
        message=OBMessage(text), font=0, sender={'user_id':sender_id, 'nickname':'群友'})
    if group:
        data.update(group_id=123, message_type='group')
        return GroupMessageEvent.model_validate(data)
    data['message_type'] = 'private'
    return PrivateMessageEvent.model_validate(data)


def test_session_keys_separate_bot_group_and_private(settings):
    bot = SimpleNamespace(self_id='999')
    group = transport.from_event(bot, event()).effective_chat.id
    private_event = event(False, sender_id=123)
    private = transport.from_event(bot, private_event).effective_chat.id
    other_bot = transport.from_event(SimpleNamespace(self_id='888'), event()).effective_chat.id
    assert len({group, private, other_bot}) == 3


def test_mentions_and_quoted_bot_are_native_fields(settings):
    value = event(text='[CQ:at,qq=999]你好')
    value.reply = SimpleNamespace(message_id=5, sender=SimpleNamespace(user_id=999,nickname='bot'))
    msg = transport.from_event(SimpleNamespace(self_id='999'), value).effective_message
    assert msg.mentioned_bot
    assert decision._is_reply_to_bot(msg, 999)
    assert decision._has_name_mentioned('ナナセ，帮我看看')
    assert decision._is_direct_request('ナナセ，帮我看看', True)


@pytest.mark.parametrize('hour', [0, 5, 6, 21, 22, 23])
@pytest.mark.parametrize('enabled', [True, False])
async def test_group_input_reaches_policy_throughout_the_day(settings, hour, enabled):
    msg = message()
    now = datetime(2026, 11, 1, hour, tzinfo=decision.TZ_UTC8)
    with patch.object(decision, '_now_utc8', return_value=now), \
         patch.object(decision, 'get_user_ai_data_async', new_callable=AsyncMock,
                      return_value={'favorability': 20, 'is_enabled': enabled}), \
         patch.object(decision, '_peek_continuation', new_callable=AsyncMock, return_value=False), \
         patch.object(decision.context_store, 'append_context_message_async', new_callable=AsyncMock) as append, \
         patch.object(decision, '_schedule_compaction'), \
         patch.object(decision.debounce, 'schedule', return_value=True) as schedule:
        await decision.handle_ai_update(Update(msg), msg.get_bot(), SimpleNamespace(id=999, username=''))
    append.assert_awaited_once()
    schedule.assert_called_once()
    assert schedule.call_args.kwargs['priority'] is False


async def test_text_cannot_inject_onebot_segments(settings):
    bot = SimpleNamespace(self_id='999', send_msg=AsyncMock())
    await transport.QQTransport(bot).send_message('999:group:123', '[CQ:at,qq=all]', reply_to=7)
    payload = bot.send_msg.await_args.kwargs['message']
    assert [item.type for item in payload] == ['reply','text']
    assert payload[1].data['text'] == '[CQ:at,qq=all]'


async def test_group_registration_and_private_admission(settings):
    with patch.object(access.db,'ensure_user_async',new_callable=AsyncMock) as register, \
         patch.object(access.db,'is_user_known_async',new_callable=AsyncMock,return_value=True):
        assert await access.check_access_async(Update(message()))
        register.assert_awaited_once_with(42)
        register.reset_mock()
        assert await access.check_access_async(Update(message(True)))
        register.assert_not_awaited()
    settings.soruto_allowed_groups.clear()
    with patch.object(access.db,'ensure_user_async',new_callable=AsyncMock) as register:
        assert not await access.check_access_async(Update(message()))
        register.assert_not_awaited()


async def test_banned_and_unknown_users_are_silent(settings):
    with patch.object(access.db,'is_user_known_async',new_callable=AsyncMock,return_value=False):
        assert not await access.check_access_async(Update(message(True)))
    settings.soruto_banned_users.add(42)
    with patch.object(access.db,'is_user_known_async',new_callable=AsyncMock) as known:
        assert not await access.check_access_async(Update(message(True)))
        known.assert_not_awaited()


async def test_entry_routes_commands_without_consuming_others(settings, monkeypatch):
    monkeypatch.setattr(plugin,'_ready',True)
    bot = SimpleNamespace(self_id='999')
    with patch.object(access,'check_access_async',new_callable=AsyncMock,return_value=True), \
         patch.object(plugin.commands,'handle_summary_command',new_callable=AsyncMock) as summary, \
         patch.object(decision,'handle_ai_update',new_callable=AsyncMock) as chat:
        assert await plugin.handle_event(bot,event(text='/summary'))
        summary.assert_awaited_once()
        assert not await plugin.handle_event(bot,event(text='mai.登录 credentials'))
        assert not await plugin.handle_event(bot,event(text='/other'))
        chat.assert_not_awaited()
        assert not await plugin.handle_event(bot,event(text='你好'))
        assert chat.await_args.kwargs['request_context'].from_user.id == 42


async def test_http_chain_and_json_modes(settings, monkeypatch):
    requests = []
    settings.soruto_simple_models=['first','backup']
    async def respond(request):
        payload=json.loads(request.content)
        requests.append(payload)
        if payload['model']=='first':
            return httpx.Response(429)
        return httpx.Response(200,json={'choices':[{'message':{'content':'{"ok":true}'}}]})
    async with httpx.AsyncClient(base_url='https://api.deepseek.com', transport=httpx.MockTransport(respond)) as client:
        monkeypatch.setattr(llm,'_client',client)
        monkeypatch.setattr(llm,'_slots',asyncio.Semaphore(1))
        assert await llm.chat_text_async('JSON please',purpose='decision')=='{"ok":true}'
        assert [r['model'] for r in requests]==['first','backup']
        assert requests[0]['response_format']=={'type':'json_object'}
        requests.clear()
        settings.soruto_simple_models=['backup']
        await llm.chat_text_async('hello')
        assert 'response_format' not in requests[0]


async def test_refusal_and_request_errors_do_not_fallback(settings, monkeypatch):
    settings.soruto_simple_models=['first','backup']
    for status, body in [(200,{'choices':[{'message':{'content':'不能帮助此请求'}}]}),(400,{'error':'invalid'})]:
        calls=[]
        async def respond(request):
            calls.append(request)
            return httpx.Response(status,json=body)
        async with httpx.AsyncClient(base_url='https://api.deepseek.com',transport=httpx.MockTransport(respond)) as client:
            monkeypatch.setattr(llm,'_client',client)
            monkeypatch.setattr(llm,'_slots',asyncio.Semaphore(1))
            await llm.chat_text_async('hello')
            assert len(calls)==1


async def test_tool_loop_returns_reasoning_and_real_results(settings, monkeypatch):
    requests=[]
    tool_call={'id':'call-1','type':'function','function':{'name':'web_search','arguments':'{"query":"舞萌"}'}}
    async def respond(request):
        data=json.loads(request.content)
        requests.append(data)
        msg=({'content':None,'reasoning_content':'internal-only','tool_calls':[tool_call]} if len(requests)==1
             else {'content':'来源：https://example.com/result'})
        return httpx.Response(200,json={'choices':[{'message':msg}]})
    registry=tools.Registry()
    registry.tools={'web_search':tools.Tool('web_search','search',{'type':'object'},True)}
    registry.execute=AsyncMock(return_value='{"url":"https://example.com/result"}')
    monkeypatch.setattr(tools,'registry',registry)
    async with httpx.AsyncClient(base_url='https://api.deepseek.com',transport=httpx.MockTransport(respond)) as client:
        monkeypatch.setattr(llm,'_client',client)
        monkeypatch.setattr(llm,'_slots',asyncio.Semaphore(1))
        text=await llm.agent_text_async(message(True),'search',use_tools=True)
    assert 'example.com/result' in text
    assert requests[1]['messages'][-2]['reasoning_content']=='internal-only'
    assert requests[1]['messages'][-1]['role']=='tool'
    registry.execute.assert_awaited_once()


async def test_failure_after_tool_start_never_replays(settings, monkeypatch):
    settings.soruto_complex_models=['first','backup']
    call={'id':'c1','type':'function','function':{'name':'web_search','arguments':'{"query":"x"}'}}
    request=AsyncMock(side_effect=[{'content':None,'tool_calls':[call]},TimeoutError()])
    monkeypatch.setattr(llm,'_request',request)
    registry=tools.Registry()
    registry.tools={'web_search':tools.Tool('web_search','search',{'type':'object'},True)}
    registry.execute=AsyncMock(return_value='real result')
    monkeypatch.setattr(tools,'registry',registry)
    assert await llm.agent_text_async(message(True),'search',use_tools=True) is None
    assert [args.args[0] for args in request.await_args_list]==['first','first']
    registry.execute.assert_awaited_once()


def test_visual_requests_never_reach_pro(settings):
    assert llm._chain('complex',True)==['deepseek-flash']
    with pytest.raises(ValueError):
        Config(soruto_vision_models=['deepseek-v4-pro'])


def test_casual_mcp_requires_both_explicit_readonly_and_whitelist(settings):
    settings.soruto_mcp_servers={'repo':MCPServer(url='https://example.com/mcp',allowed_tools=['read','write'],readonly_tools=['read'])}
    registry=tools.Registry()
    read=tools.Tool('read_alias','read',{},True,'repo','read')
    write=tools.Tool('write_alias','write',{},False,'repo','write')
    assert not registry.permitted(read,message(),True)
    config.CASUAL_TOOL_NAMES=['repo/read','repo/write']
    assert registry.permitted(read,message(),True)
    assert not registry.permitted(write,message(),True)
    settings.soruto_mcp_servers['repo'].allowed_users={777}
    assert not registry.permitted(read,message(),False)


def test_skills_cannot_escape_the_enabled_directory(settings,tmp_path):
    directory=tmp_path/'demo'
    directory.mkdir()
    (directory/'SKILL.md').write_text('---\nname: demo\ndescription: test\n---\nRead only.',encoding='utf-8')
    (tmp_path/'secret.txt').write_text('private',encoding='utf-8')
    settings.soruto_skills_dir=tmp_path
    settings.soruto_enabled_skills={'demo'}
    skills.initialize()
    assert 'Read only' in skills.read('demo')
    with pytest.raises(ValueError):
        skills.read('demo','../secret.txt')
    with pytest.raises(ValueError):
        skills.read('missing')


def test_knowledge_chunks_preserve_text_and_pdf_docx_extractors(tmp_path):
    from docx import Document
    from pypdf import PdfWriter
    doc=Document()
    doc.add_paragraph('本地知识库测试')
    path=tmp_path/'test.docx'
    doc.save(path)
    assert '本地知识库测试' in knowledge.read_document(path)
    pdf=PdfWriter()
    pdf.add_blank_page(width=100,height=100)
    path=tmp_path/'blank.pdf'
    pdf.write(path)
    assert knowledge.read_document(path)==''
    text='abcdefghij'*500
    assert knowledge.chunks(text)[0].endswith(knowledge.chunks(text)[1][:120])
