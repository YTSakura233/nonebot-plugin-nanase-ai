import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from nonebot_plugin_soruto_ai.core import debounce


class DebounceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self):
        await debounce.close()

    async def test_fragments_run_only_latest_callback(self):
        first, last = AsyncMock(), AsyncMock()
        with patch.object(debounce, "DEBOUNCE_SECONDS", 0.005):
            debounce.schedule(1, first, user_id=10)
            debounce.schedule(1, last, user_id=10)
            await asyncio.wait_for(asyncio.gather(*(s.task for s in debounce._pending.values())), 1)
        first.assert_not_awaited()
        last.assert_awaited_once()

    async def test_unmentioned_fragment_preserves_directed_request(self):
        directed, fragment = AsyncMock(), AsyncMock()
        with patch.object(debounce, "DEBOUNCE_SECONDS", 0.005):
            debounce.schedule(1, directed, priority=True, user_id=10)
            debounce.schedule(1, fragment, user_id=10)
            await asyncio.wait_for(asyncio.gather(*(s.task for s in debounce._pending.values())), 1)
        directed.assert_awaited_once()
        fragment.assert_not_awaited()

    async def test_different_users_direct_questions_are_not_lost(self):
        first, second = AsyncMock(), AsyncMock()
        with patch.object(debounce, "DEBOUNCE_SECONDS", 0.005):
            debounce.schedule(1, first, priority=True, user_id=10)
            debounce.schedule(1, second, priority=True, user_id=20)
            await asyncio.wait_for(asyncio.gather(*(s.task for s in debounce._pending.values())), 1)
        first.assert_awaited_once()
        second.assert_awaited_once()

    async def test_reset_cancels_running_reply(self):
        started, stopped = asyncio.Event(), asyncio.Event()
        async def slow_reply():
            started.set()
            try:
                await asyncio.sleep(30)
            finally:
                stopped.set()
        with patch.object(debounce, "DEBOUNCE_SECONDS", 0):
            debounce.schedule(1, slow_reply)
            await asyncio.wait_for(started.wait(), 1)
            before = debounce.current_revision(1)
            debounce.cancel_chat(1)
            await asyncio.wait_for(stopped.wait(), 1)
            self.assertGreater(debounce.current_revision(1), before)

    async def test_cancelling_one_chat_keeps_another(self):
        first, second = AsyncMock(), AsyncMock()
        with patch.object(debounce, "DEBOUNCE_SECONDS", 0.005):
            debounce.schedule(1, first)
            debounce.schedule(2, second)
            debounce.cancel_chat(1)
            await asyncio.wait_for(asyncio.gather(*(s.task for s in debounce._pending.values())), 1)
        first.assert_not_awaited()
        second.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
