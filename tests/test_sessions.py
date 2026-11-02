import asyncio
import sys
import unittest
from contextlib import ExitStack, contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from nonebot_plugin_soruto_ai.core import commands, config, context_store, debounce


class SessionCommandTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        commands._pending.clear()
        self.bot = SimpleNamespace(get_chat_member=AsyncMock(return_value=SimpleNamespace(status="creator")))

    def message(self, text, *, chat_id=-99, user_id=42, private=False, anonymous=False):
        return SimpleNamespace(text=text, caption=None, chat_id=chat_id,
                               chat=SimpleNamespace(type="private" if private else "supergroup"),
                               from_user=SimpleNamespace(id=user_id), sender_chat=object() if anonymous else None,
                               get_bot=lambda: self.bot)

    @contextmanager
    def mocked(self):
        with ExitStack() as stack:
            state = SimpleNamespace()
            for target, name, result in (
                (commands, "safe_reply_text", None), (context_store, "compact_session_async", True),
                (context_store, "reset_session_async", None), (commands, "reset_user_ai_data_async", None),
            ):
                setattr(state, name, stack.enter_context(patch.object(target, name, new_callable=AsyncMock, return_value=result)))
            state.cancel = stack.enter_context(patch.object(debounce, "cancel_chat"))
            state.report = stack.enter_context(patch.object(commands, "report_exception"))
            yield state

    async def test_member_and_administrator_cannot_manage_session(self):
        for status in ("member", "administrator", "restricted"):
            for sub in ("compact", "reset", "reset confirm"):
                with self.subTest(status=status, sub=sub), self.mocked() as state:
                    self.bot.get_chat_member.return_value = SimpleNamespace(status=status)
                    await commands.handle_ai_command(self.message("/ai " + sub))
                    state.compact_session_async.assert_not_awaited()
                    state.reset_session_async.assert_not_awaited()
                    assert state.safe_reply_text.await_args is not None
                    self.assertIn("群所有者", state.safe_reply_text.await_args.args[1])

    async def test_original_on_off_feedback_is_preserved(self):
        with (
            self.mocked() as state,
            patch.object(commands, "get_user_ai_data_async", new_callable=AsyncMock,
                         return_value={"favorability": 20, "is_enabled": True}),
            patch.object(commands, "set_user_ai_enabled_async", new_callable=AsyncMock),
        ):
            await commands.handle_ai_command(self.message("/ai on"))
            await commands.handle_ai_command(self.message("/ai off"))
            texts = [call.args[1] for call in state.safe_reply_text.await_args_list]
            self.assertEqual(texts, ["✅ 已开启 ナナセ ，喵喵~", "✅ 已关闭 ナナセ 回复qwq"])

    async def test_owner_can_compact(self):
        with self.mocked() as state:
            await commands.handle_ai_command(self.message("/ai compact"))
            state.compact_session_async.assert_awaited_once_with(-99)
            state.cancel.assert_called_once_with(-99)

    async def test_private_user_can_compact_without_group_lookup(self):
        with self.mocked() as state:
            await commands.handle_ai_command(self.message("/ai compact", private=True, chat_id=42))
            state.compact_session_async.assert_awaited_once_with(42)
            self.bot.get_chat_member.assert_not_awaited()

    async def test_reset_needs_same_chat_and_user_confirmation_and_keeps_long_term_data(self):
        with self.mocked() as state:
            await commands.handle_ai_command(self.message("/ai reset"))
            state.reset_session_async.assert_not_awaited()
            await commands.handle_ai_command(self.message("/ai reset confirm", chat_id=-98))
            await commands.handle_ai_command(self.message("/ai reset confirm", user_id=43))
            state.reset_session_async.assert_not_awaited()
            await commands.handle_ai_command(self.message("/ai reset confirm"))
            state.reset_session_async.assert_awaited_once_with(-99)
            state.reset_user_ai_data_async.assert_not_awaited()

    async def test_private_reset_uses_same_confirmation_flow(self):
        with self.mocked() as state:
            await commands.handle_ai_command(self.message("/ai reset", private=True, chat_id=42))
            await commands.handle_ai_command(self.message("/ai reset confirm", private=True, chat_id=42))
            state.reset_session_async.assert_awaited_once_with(42)
            self.bot.get_chat_member.assert_not_awaited()

    async def test_owner_is_rechecked_at_confirmation(self):
        with self.mocked() as state:
            await commands.handle_ai_command(self.message("/ai reset"))
            self.bot.get_chat_member.return_value = SimpleNamespace(status="administrator")
            await commands.handle_ai_command(self.message("/ai reset confirm"))
            state.reset_session_async.assert_not_awaited()
            self.assertEqual(self.bot.get_chat_member.await_count, 2)

    async def test_expired_confirmation_cannot_reset(self):
        with self.mocked() as state, patch.object(commands.time, "monotonic", return_value=100) as clock:
            await commands.handle_ai_command(self.message("/ai reset"))
            clock.return_value = 300
            await commands.handle_ai_command(self.message("/ai reset confirm"))
            state.reset_session_async.assert_not_awaited()

    async def test_anonymous_identity_is_not_accepted_as_owner(self):
        with self.mocked() as state:
            await commands.handle_ai_command(self.message("/ai compact", anonymous=True))
            state.compact_session_async.assert_not_awaited()
            self.bot.get_chat_member.assert_not_awaited()

    async def test_identity_lookup_failure_fails_closed_without_exception_text(self):
        self.bot.get_chat_member.side_effect = RuntimeError("secret database/address")
        with self.mocked() as state:
            await commands.handle_ai_command(self.message("/ai reset"))
            state.reset_session_async.assert_not_awaited()
            state.report.assert_called_once()
            assert state.safe_reply_text.await_args is not None
            self.assertNotIn("secret", state.safe_reply_text.await_args.args[1])

    async def test_old_personal_forget_confirmation_cannot_reset_session(self):
        commands._set_pending(-99, 42, "forget")
        with self.mocked() as state:
            await commands.handle_ai_command(self.message("/ai reset confirm"))
            state.reset_session_async.assert_not_awaited()
            state.reset_user_ai_data_async.assert_not_awaited()

    async def test_compact_rejects_extra_arguments_without_storage_calls(self):
        with self.mocked() as state:
            await commands.handle_ai_command(self.message("/ai compact everything"))
            state.compact_session_async.assert_not_awaited()
            state.report.assert_not_called()


class _AsyncContext:
    def __init__(self, value):
        self.value = value
    async def __aenter__(self):
        return self.value
    async def __aexit__(self, *args):
        return False


class SessionStoreTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        context_store._compact_locks.clear()
        context_store._write_locks.clear()
        self.cursor = SimpleNamespace(execute=AsyncMock())
        self.connection = SimpleNamespace(cursor=lambda: _AsyncContext(self.cursor),
                                          commit=AsyncMock(), rollback=AsyncMock())

    @contextmanager
    def compact_fixture(self):
        with ExitStack() as stack:
            for name, result in (("_context_size_async", (2, 100)),
                                 ("_fetch_oldest_for_compaction_async", [(10, "user", "群友", "事实")]),
                                 ("get_chat_summary_async", "旧摘要")):
                stack.enter_context(patch.object(context_store, name, new_callable=AsyncMock, return_value=result))
            commit = stack.enter_context(patch.object(context_store, "_commit_compaction_async", new_callable=AsyncMock))
            stack.enter_context(patch.object(config, "LLM_DEADLINE_SECONDS", 5))
            yield commit

    async def test_failed_model_does_not_delete_original_context(self):
        with self.compact_fixture() as commit, patch.object(context_store, "_summarize", new_callable=AsyncMock, return_value=None):
            self.assertFalse(await context_store.compact_session_async(-99))
            commit.assert_not_awaited()

    async def test_success_compacts_snapshot_only(self):
        with self.compact_fixture() as commit, patch.object(context_store, "_summarize", new_callable=AsyncMock, return_value="事实与待办"):
            self.assertTrue(await context_store.compact_session_async(-99))
            commit.assert_awaited_once_with(-99, "事实与待办", 10)

    async def test_compaction_commit_and_delete_share_transaction(self):
        with patch.object(context_store, "get_db_connection_async", return_value=_AsyncContext(self.connection)):
            await context_store._commit_compaction_async(-99, "摘要", 10)
        calls = self.cursor.execute.await_args_list
        self.assertEqual(len(calls), 2)
        self.assertIn("INSERT INTO soruto_nb_chat_summary", calls[0].args[0])
        self.assertIn("seq <= %s", calls[1].args[0])
        self.assertEqual(calls[1].args[1], (-99, 10))
        self.connection.commit.assert_awaited_once()

    async def test_failed_delete_rolls_back_summary(self):
        self.cursor.execute.side_effect = [None, RuntimeError("write failed")]
        with patch.object(context_store, "get_db_connection_async", return_value=_AsyncContext(self.connection)):
            with self.assertRaises(RuntimeError):
                await context_store._commit_compaction_async(-99, "摘要", 10)
        self.connection.rollback.assert_awaited_once()
        self.connection.commit.assert_not_awaited()

    async def test_reset_only_deletes_current_chat_context_and_summary(self):
        with patch.object(context_store, "get_db_connection_async", return_value=_AsyncContext(self.connection)):
            await context_store.reset_session_async(-99)
        calls = self.cursor.execute.await_args_list
        self.assertEqual([c.args[0] for c in calls], [
            "DELETE FROM soruto_nb_chat_context WHERE chat_id = %s", "DELETE FROM soruto_nb_chat_summary WHERE chat_id = %s"])
        self.assertTrue(all(c.args[1] == (-99,) for c in calls))
        self.connection.commit.assert_awaited_once()

    async def test_reset_waits_for_shared_session_lock(self):
        lock = context_store.session_lock(-99)
        await lock.acquire()
        try:
            with patch.object(context_store, "get_db_connection_async", return_value=_AsyncContext(self.connection)):
                task = asyncio.create_task(context_store.reset_session_async(-99))
                await asyncio.sleep(0)
                self.cursor.execute.assert_not_awaited()
                lock.release()
                await asyncio.wait_for(task, 1)
        finally:
            if lock.locked():
                lock.release()
        self.connection.commit.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
