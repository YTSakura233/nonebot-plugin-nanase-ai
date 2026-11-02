"""跨真实决策路径验证串行发送、过期结果和既有群聊策略。"""
import asyncio
import sys
import unittest
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from nonebot_plugin_soruto_ai.core import config, context_store, debounce, decision


class ReplyFlowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        context_store._compact_locks.clear()
        context_store._write_locks.clear()

    @contextmanager
    def flow(self, *, enabled=True, response=None, history=None):
        rows = list(history or [])
        response = response or {"message": "这是同一个回答喵", "sticker": "", "affinity_delta": 2, "memory_events": []}
        state = SimpleNamespace(rows=rows)
        with ExitStack() as stack:
            def mock_async(target, name, value=None, **kwargs):
                return stack.enter_context(patch.object(target, name, new_callable=AsyncMock, return_value=value, **kwargs))
            mock_async(decision, "get_user_ai_data_async", {"favorability": 20, "is_enabled": enabled})
            async def recent(*_args, **_kwargs):
                await asyncio.sleep(0)
                return list(rows)
            mock_async(context_store, "get_recent_context_async", side_effect=recent)
            mock_async(context_store, "get_chat_summary_async", "")
            state.cross_chat = mock_async(context_store, "get_cross_chat_user_thread_async", [])
            state.retrieve = mock_async(decision.memory_store, "retrieve_relevant_facts_async", ([], [], []))
            mock_async(decision.memory_store, "retrieve_relevant_knowledge_async", ([], []))
            mock_async(decision.llm, "kb_retrieve_async", [])
            mock_async(decision.llm, "chat_text_async", '{"duplicate":false,"appropriate":true}')
            state.model = mock_async(decision, "call_main_model_async", response)
            state.sent = mock_async(decision, "_send_with_typing", True)
            state.affinity = mock_async(decision, "update_user_favorability_async")
            state.memory = mock_async(decision.memory_store, "apply_memory_events_async")
            state.hits = mock_async(decision.memory_store, "bump_hit_count_async")
            async def append(**row):
                rows.append({**row, "created_at": datetime.now(timezone.utc), "seq": len(rows) + 1})
            state.append = mock_async(context_store, "append_context_message_async", side_effect=append)
            stack.enter_context(patch.object(decision, "_logger", return_value=Mock()))
            stack.enter_context(patch.object(config, "ENABLE_TOOLS", True))
            stack.enter_context(patch.object(config, "LLM_DEADLINE_SECONDS", 5))
            yield state

    async def run_reply(self, **overrides):
        args: dict = dict(bot=Mock(), chat_id=-321, chat_type="supergroup", user_id=42, user_name="群友",
                    message=SimpleNamespace(chat_id=-321, reply_to_message=None), rendered="接着聊",
                    is_at=False, is_reply_to_you=False, name_mentioned=False, direct_request=False)
        args.update(overrides)
        await decision._decide_and_respond(**args)

    async def test_concurrent_casual_generations_emit_one_reply(self):
        with self.flow() as state:
            await asyncio.gather(self.run_reply(), self.run_reply(user_id=43))
            self.assertEqual(state.sent.await_count, 1)
            self.assertEqual(state.append.await_count, 1)
            state.affinity.assert_not_awaited()

    async def test_two_explicit_questions_are_not_deduplicated(self):
        with self.flow() as state:
            await asyncio.gather(self.run_reply(is_at=True), self.run_reply(user_id=43, is_at=True))
            self.assertEqual(state.sent.await_count, 2)

    async def test_private_chat_can_use_tools_without_mention(self):
        with self.flow() as state:
            await self.run_reply(chat_type="private")
            assert state.model.await_args is not None
            self.assertTrue(state.model.await_args.kwargs["use_tools"])

    async def test_ai_off_private_and_directed_are_silent(self):
        with self.flow(enabled=False) as state:
            await self.run_reply(chat_type="private")
            await self.run_reply(is_at=True)
            state.model.assert_not_awaited()

    async def test_ai_off_can_still_casually_talk_without_reply_or_affinity(self):
        with self.flow(enabled=False) as state:
            await self.run_reply()
            state.sent.assert_awaited_once()
            assert state.sent.await_args is not None
            self.assertFalse(state.sent.await_args.kwargs["as_reply"])
            state.affinity.assert_not_awaited()

    async def test_casual_chat_is_available_at_every_hour(self):
        for hour in range(24):
            for enabled in (True, False):
                with self.subTest(hour=hour, enabled=enabled), self.flow(enabled=enabled) as state:
                    now = datetime(2026, 11, 1, hour, tzinfo=decision.TZ_UTC8)
                    with patch.object(decision, '_now_utc8', return_value=now):
                        await self.run_reply()
                    state.model.assert_awaited_once()
                    state.sent.assert_awaited_once()
                    self.assertFalse(state.sent.await_args.kwargs['as_reply'])
                    self.assertEqual(state.append.await_args.kwargs['name'], 'ナナセ')
                    state.affinity.assert_not_awaited()

    async def test_ai_off_stays_silent_for_directed_messages_at_night(self):
        now = datetime(2026, 11, 1, 2, tzinfo=decision.TZ_UTC8)
        with self.flow(enabled=False) as state, patch.object(decision, '_now_utc8', return_value=now):
            await self.run_reply(chat_type='private')
            await self.run_reply(is_at=True)
            state.model.assert_not_awaited()

    async def test_public_chat_does_not_load_other_chat_transcripts(self):
        with self.flow() as state:
            await self.run_reply()
            state.cross_chat.assert_not_awaited()
            assert state.retrieve.await_args is not None
            self.assertFalse(state.retrieve.await_args.kwargs["allow_private"])

    async def test_stale_casual_result_does_not_send_or_write_memory(self):
        response = {"message": "旧回答", "sticker": "", "affinity_delta": 2,
                    "memory_events": [{"action": "add", "scope": "user", "fact": "过期内容"}]}
        with self.flow(response=response) as state:
            revision = debounce.touch(-321)
            async def generate(*args, **kwargs):
                debounce.touch(-321)
                return response
            state.model.side_effect = generate
            await self.run_reply(revision=revision)
            state.sent.assert_not_awaited()
            state.memory.assert_not_awaited()

    async def test_failed_send_is_not_written_as_successful_turn(self):
        with self.flow() as state:
            state.sent.return_value = False
            await self.run_reply(is_at=True)
            state.append.assert_not_awaited()
            state.affinity.assert_not_awaited()

    async def test_sticker_only_response_is_not_sent_or_recorded(self):
        response = {"message": "", "sticker": "🤔", "affinity_delta": 0, "memory_events": []}
        history = [{"role": "assistant", "text": "[贴纸 🤔]", "user_id": None,
                    "created_at": datetime.now(timezone.utc), "name": "ナナセ"}]
        with self.flow(response=response, history=history) as state:
            await self.run_reply()
            state.sent.assert_not_awaited()
            state.append.assert_not_awaited()
            state.affinity.assert_not_awaited()

    async def test_emoji_is_sent_with_text_and_recorded_in_same_turn(self):
        response = {"message": "在这里呀", "sticker": "🤔", "affinity_delta": 2, "memory_events": []}
        with self.flow(response=response) as state:
            await self.run_reply(is_at=True)
            state.sent.assert_awaited_once()
            self.assertEqual(state.sent.await_args.args[2], '🤔 在这里呀')
            state.append.assert_awaited_once()
            self.assertEqual(state.append.await_args.kwargs['text'], '🤔 在这里呀')

    async def test_emoji_already_in_body_is_not_appended_twice(self):
        response = {"message": "在这里呀 🤔", "sticker": "🤔", "affinity_delta": 0, "memory_events": []}
        with self.flow(response=response) as state:
            await self.run_reply(is_at=True)
            state.sent.assert_awaited_once()
            self.assertEqual(state.sent.await_args.args[2], '在这里呀 🤔')

    async def test_combined_emoji_reply_is_checked_for_duplicates(self):
        response = {"message": "在这里呀", "sticker": "🤔", "affinity_delta": 0, "memory_events": []}
        history = [{"role":"assistant", "text":"🤔 在这里呀", "user_id":None,
                    "created_at":datetime.now(timezone.utc),"name":"ナナセ"}]
        with self.flow(response=response,history=history) as state:
            await self.run_reply()
            state.sent.assert_not_awaited()
            state.append.assert_not_awaited()

    async def test_long_text_does_not_leave_selected_emoji_in_its_own_chunk(self):
        text = decision._inline_emoji('正文'*2000,'🤔')
        parts = decision._split_reply(text,200)
        self.assertTrue(parts[0].startswith('🤔 正文'))
        self.assertTrue(all(part.strip()!='🤔' for part in parts))

    async def test_model_cannot_enter_breakthrough_without_confirmation(self):
        with self.flow() as state, patch.object(decision,'get_user_ai_data_async',new_callable=AsyncMock,
                return_value={'favorability':100,'is_enabled':True}):
            await self.run_reply(is_at=True)
            state.sent.assert_awaited_once()
            state.affinity.assert_not_awaited()

    async def asyncTearDown(self):
        await debounce.close()


if __name__ == "__main__":
    unittest.main()
