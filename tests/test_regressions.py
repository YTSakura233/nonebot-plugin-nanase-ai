"""在真实命令/回复路径注入固定模型结果，不连接 Telegram、数据库或模型。"""
import sys
import unittest
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from nonebot_plugin_soruto_ai.core import commands, decision


class ConversationRegressions(unittest.IsolatedAsyncioTestCase):
    async def test_group_administrator_cannot_reset_session(self):
        bot = SimpleNamespace(get_chat_member=AsyncMock(return_value=SimpleNamespace(status="administrator")))
        message = SimpleNamespace(
            from_user=SimpleNamespace(id=42), chat_id=-100,
            chat=SimpleNamespace(type="supergroup"), text="/ai reset", caption=None,
            get_bot=lambda: bot,
        )
        with (
            patch.object(commands, "safe_reply_text", new_callable=AsyncMock) as reply,
            patch.object(commands, "get_user_ai_data_async", new_callable=AsyncMock,
                         return_value={"favorability": 20, "is_enabled": True}),
            patch.object(commands, "get_reset_cooldown_async", new_callable=AsyncMock, return_value=None),
            patch.object(commands, "reset_user_ai_data_async", new_callable=AsyncMock) as reset,
        ):
            await commands.handle_ai_command(message)
            assert reply.await_args is not None
            self.assertIn("群所有者", reply.await_args.args[1])
            reset.assert_not_awaited()

    async def test_near_duplicate_casual_reply_is_not_sent(self):
        previous = "只在冲榜的时候查，平时那些痕迹就放过去了喵"
        history = [{"seq": 1, "role": "assistant", "name": "ナナセ", "text": previous,
                    "user_id": None, "created_at": datetime.now(timezone.utc)}]
        response = {"message": previous + "。", "sticker": "", "affinity_delta": 0, "memory_events": []}
        with ExitStack() as stack:
            def mock_async(target, name, value=None):
                return stack.enter_context(patch.object(target, name, new_callable=AsyncMock, return_value=value))
            mock_async(decision, "get_user_ai_data_async", {"favorability": 20, "is_enabled": True})
            mock_async(decision.context_store, "get_recent_context_async", history)
            mock_async(decision.context_store, "get_chat_summary_async", "")
            mock_async(decision.context_store, "get_cross_chat_user_thread_async", [])
            mock_async(decision.memory_store, "retrieve_relevant_facts_async", ([], [], []))
            mock_async(decision.memory_store, "fetch_stable_group_facts_async", ([], []))
            mock_async(decision.memory_store, "retrieve_relevant_knowledge_async", ([], []))
            mock_async(decision.llm, "kb_retrieve_async", [])
            mock_async(decision, "call_main_model_async", response)
            sent = mock_async(decision, "_send_with_typing")
            mock_async(decision.context_store, "append_context_message_async")
            stack.enter_context(patch.object(decision, "_logger", return_value=Mock()))
            await decision._decide_and_respond(
                bot=Mock(), chat_id=-100, chat_type="supergroup", user_id=42,
                user_name="群友", message=SimpleNamespace(chat_id=-100), rendered="那也太草台班子了",
                is_at=False, is_reply_to_you=False, name_mentioned=False, direct_request=False,
            )
            sent.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
