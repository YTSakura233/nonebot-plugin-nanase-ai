import asyncio
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from nonebot_plugin_soruto_ai.core import debounce, decision


class LateInputTests(unittest.IsolatedAsyncioTestCase):
    async def test_reset_discards_input_still_waiting_for_media(self):
        started, release = asyncio.Event(), asyncio.Event()
        async def extract(*args):
            started.set()
            await release.wait()
            return "旧问题", False, []
        message = SimpleNamespace(chat_id=-991, reply_to_message=None, message_id=1)
        update = SimpleNamespace(effective_message=message,
                                 effective_user=SimpleNamespace(id=42, full_name="群友", username=None),
                                 effective_chat=SimpleNamespace(id=-991, type="group"))
        with (
            patch.object(decision, "_extract_text_and_media", side_effect=extract),
            patch.object(decision, "get_user_ai_data_async", new_callable=AsyncMock,
                         return_value={"favorability": 20, "is_enabled": True}),
            patch.object(decision, "is_bot_mentioned", return_value=True),
            patch.object(decision, "_logger", return_value=Mock()),
            patch.object(decision.context_store, "append_context_message_async", new_callable=AsyncMock) as append,
            patch.object(decision, "_schedule_compaction"),
            patch.object(debounce, "schedule") as schedule,
        ):
            task = asyncio.create_task(decision.handle_ai_update(update, object(), SimpleNamespace(id=1, username="bot")))
            await asyncio.wait_for(started.wait(), 1)
            debounce.cancel_chat(-991)
            release.set()
            await asyncio.wait_for(task, 1)
            append.assert_not_awaited()
            schedule.assert_not_called()

    async def asyncTearDown(self):
        await debounce.close()


if __name__ == "__main__":
    unittest.main()
