import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from nonebot_plugin_soruto_ai.core import reply_guard


class ReplyGuardTests(unittest.IsolatedAsyncioTestCase):
    def rows(self, text, age=0):
        return [{"role": "assistant", "text": text, "created_at": datetime.now(timezone.utc) - timedelta(seconds=age)}]

    async def review(self, text, history):
        return await reply_guard.should_suppress(text, history, current_message="群员正在讨论这件事")

    async def test_punctuation_only_change_is_duplicate_without_model(self):
        with patch.object(reply_guard.llm, "chat_text_async", new_callable=AsyncMock) as classify:
            self.assertTrue(await self.review("同样的意思喵。", self.rows("同样的意思喵")))
            classify.assert_not_awaited()

    async def test_paraphrase_uses_semantic_verdict(self):
        with patch.object(reply_guard.llm, "chat_text_async", new_callable=AsyncMock,
                          return_value='{"appropriate":true,"duplicate":true}'):
            self.assertTrue(await self.review(
                "只在冲榜查的话，平时那些痕迹不就放过去了喵", self.rows("只在冲榜的时候查，平时的洞不就白放着了喵")))

    async def test_correction_is_not_discarded(self):
        with patch.object(reply_guard.llm, "chat_text_async", new_callable=AsyncMock,
                          return_value='{"appropriate":true,"duplicate":false}'):
            self.assertFalse(await self.review("更正：需要 3 次", self.rows("需要 2 次")))

    async def test_changed_negative_number_is_not_normalized_as_same(self):
        with patch.object(reply_guard.llm, "chat_text_async", new_callable=AsyncMock,
                          return_value='{"appropriate":true,"duplicate":false}') as classify:
            self.assertFalse(await self.review("温度是 -3 度", self.rows("温度是 3 度")))
            classify.assert_awaited_once()

    async def test_old_reply_does_not_block_new_conversation(self):
        with patch.object(reply_guard.llm, "chat_text_async", new_callable=AsyncMock,
                          return_value='{"appropriate":true,"duplicate":false}') as classify:
            self.assertFalse(await self.review("早上好喵", self.rows("早上好喵", age=600)))
            assert classify.await_args is not None
            self.assertIn('"recent_bot_replies": []', classify.await_args.args[0])

    async def test_judge_outage_fails_closed_for_casual_speech(self):
        with patch.object(reply_guard.llm, "chat_text_async", new_callable=AsyncMock, return_value=None):
            self.assertTrue(await self.review("还有一个新问题", self.rows("这是之前的回答")))

    async def test_unsolicited_decline_is_blocked_even_without_previous_reply(self):
        with patch.object(reply_guard.llm, "chat_text_async", new_callable=AsyncMock,
                          return_value='{"appropriate":false,"duplicate":false}'):
            self.assertTrue(await self.review("这种事是违法的，到此为止。", []))

    async def test_unstructured_review_cannot_authorize_speech(self):
        with (
            patch.object(reply_guard.llm, "chat_text_async", new_callable=AsyncMock, return_value="可以发"),
            patch.object(reply_guard, "report_exception") as report,
        ):
            self.assertTrue(await self.review("候选内容", []))
            report.assert_called_once()


if __name__ == "__main__":
    unittest.main()
