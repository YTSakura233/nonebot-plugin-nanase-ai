import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from nonebot_plugin_soruto_ai.core import debounce, decision


class DeliveryTests(unittest.IsolatedAsyncioTestCase):
    def test_long_unicode_reply_is_split_without_losing_text(self):
        text = ("一段详细的分析 🤔\n" * 1000) + "结论"
        parts = decision._split_reply(text)
        self.assertGreater(len(parts), 1)
        self.assertEqual("".join(parts), text)
        self.assertTrue(all(len(part.encode("utf-16-le")) // 2 <= 3900 for part in parts))

    async def test_casual_reply_never_adds_reply_reference(self):
        bot = SimpleNamespace(send_chat_action=AsyncMock(), send_message=AsyncMock())
        message = SimpleNamespace(chat_id=-7)
        with (
            patch.object(decision.transport, "resolve_send_bot", return_value=bot),
            patch.object(decision, "safe_reply_text", new_callable=AsyncMock) as reply,
            patch.object(decision.asyncio, "sleep", new_callable=AsyncMock),
        ):
            self.assertTrue(await decision._send_with_typing(bot, message, "自然插一句", as_reply=False))
            reply.assert_not_awaited()
            bot.send_message.assert_awaited_once_with(chat_id=-7, text="自然插一句")

    async def test_only_first_chunk_of_directed_answer_is_quoted(self):
        bot = SimpleNamespace(send_chat_action=AsyncMock(), send_message=AsyncMock())
        message = SimpleNamespace(chat_id=-7)
        with (
            patch.object(decision.transport, "resolve_send_bot", return_value=bot),
            patch.object(decision, "safe_reply_text", new_callable=AsyncMock) as reply,
            patch.object(decision.asyncio, "sleep", new_callable=AsyncMock),
        ):
            self.assertTrue(await decision._send_with_typing(bot, message, "长" * 2500, as_reply=True))
            reply.assert_awaited_once()
            bot.send_message.assert_awaited_once()

    async def test_new_message_during_typing_discards_stale_casual_answer(self):
        bot = SimpleNamespace(send_chat_action=AsyncMock(), send_message=AsyncMock())
        revision = debounce.touch(-7)
        async def new_message(_delay):
            debounce.touch(-7)
        with (
            patch.object(decision.transport, "resolve_send_bot", return_value=bot),
            patch.object(decision.asyncio, "sleep", side_effect=new_message),
        ):
            sent = await decision._send_with_typing(bot, SimpleNamespace(chat_id=-7), "旧回复",
                                                     as_reply=False, revision=revision)
            self.assertFalse(sent)
            bot.send_message.assert_not_awaited()

    async def asyncTearDown(self):
        await debounce.close()


if __name__ == "__main__":
    unittest.main()
