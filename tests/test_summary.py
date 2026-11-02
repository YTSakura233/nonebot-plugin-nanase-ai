import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from nonebot_plugin_soruto_ai.core import commands, config, context_store, debounce


class _AsyncContext:
    def __init__(self, value):
        self.value = value
    async def __aenter__(self):
        return self.value
    async def __aexit__(self, *args):
        return False


class SummaryStoreTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        context_store._compact_locks.clear()
        self.rows = [(4, "user", "群友", "新问题"), (5, "assistant", "ナナセ", "已有回答")]
        self.cursor = SimpleNamespace(execute=AsyncMock(), fetchone=AsyncMock(return_value=("旧摘要", 3)),
                                      fetchall=AsyncMock(return_value=self.rows))
        self.conn = SimpleNamespace(cursor=lambda: _AsyncContext(self.cursor),
                                    commit=AsyncMock(), rollback=AsyncMock())
        self.db = patch.object(context_store, "get_db_connection_async", return_value=_AsyncContext(self.conn))
        self.db.start()
        self.addCleanup(self.db.stop)
        self.budget = patch.object(config, "LLM_DEADLINE_SECONDS", 5)
        self.budget.start()
        self.addCleanup(self.budget.stop)

    async def test_refresh_merges_only_new_rows_without_compacting(self):
        with (
            patch.object(context_store, "compact_session_async", new_callable=AsyncMock) as compact,
            patch.object(context_store, "get_chat_summary_async", new_callable=AsyncMock, return_value="旧摘要"),
            patch.object(context_store, "_summarize_rows_async", new_callable=AsyncMock, return_value="新摘要") as summarize,
        ):
            result = await context_store.force_refresh_summary_async(-100)
            compact.assert_not_awaited()
            self.assertEqual(result, "新摘要")
            summarize.assert_awaited_once_with("旧摘要", self.rows)
        calls = self.cursor.execute.await_args_list
        self.assertIn("seq > %s", calls[1].args[0])
        self.assertEqual(calls[1].args[1], (-100, 3))
        self.assertEqual(calls[-1].args[1], (-100, "新摘要", 5))
        self.assertTrue(all("DELETE" not in call.args[0].upper() for call in calls))
        self.conn.commit.assert_awaited_once()

    async def test_no_new_rows_reuses_summary_without_model_or_writes(self):
        self.cursor.fetchall.return_value = []
        with patch.object(context_store, "_summarize_rows_async", new_callable=AsyncMock) as summarize:
            self.assertEqual(await context_store.force_refresh_summary_async(-100), "旧摘要")
            summarize.assert_not_awaited()
        self.conn.commit.assert_not_awaited()

    async def test_empty_chat_returns_no_summary(self):
        self.cursor.fetchone.return_value = None
        self.cursor.fetchall.return_value = []
        with patch.object(context_store, "_summarize_rows_async", new_callable=AsyncMock) as summarize:
            self.assertEqual(await context_store.force_refresh_summary_async(-100), "")
            summarize.assert_not_awaited()
        self.conn.commit.assert_not_awaited()

    async def test_model_failure_does_not_update_summary_or_cursor(self):
        with patch.object(context_store, "_summarize_rows_async", new_callable=AsyncMock, return_value=None):
            with self.assertRaises(RuntimeError):
                await context_store.force_refresh_summary_async(-100)
        queries = [call.args[0].upper() for call in self.cursor.execute.await_args_list]
        self.assertTrue(all("INSERT" not in query and "DELETE" not in query for query in queries))
        self.conn.commit.assert_not_awaited()

    async def test_failed_save_rolls_back(self):
        self.cursor.execute.side_effect = [None, None, RuntimeError("save failed")]
        with patch.object(context_store, "_summarize_rows_async", new_callable=AsyncMock, return_value="新摘要"):
            with self.assertRaises(RuntimeError):
                await context_store.force_refresh_summary_async(-100)
        self.conn.rollback.assert_awaited_once()
        self.conn.commit.assert_not_awaited()

    async def test_compaction_cannot_regress_previously_refreshed_cursor(self):
        await context_store._commit_compaction_async(-100, "摘要", 2)
        query = self.cursor.execute.await_args_list[0].args[0]
        self.assertIn("GREATEST(last_seq, VALUES(last_seq))", query)


class SummaryCommandTests(unittest.IsolatedAsyncioTestCase):
    def message(self, text="/summary", *, private=False):
        return SimpleNamespace(chat_id=42 if private else -100, text=text, caption=None,
                               from_user=SimpleNamespace(id=42),
                               chat=SimpleNamespace(type="private" if private else "supergroup"))

    async def test_normal_member_can_view_summary_without_session_management(self):
        message = self.message()
        with (
            patch.object(context_store, "force_refresh_summary_async", new_callable=AsyncMock, return_value="本群摘要") as refresh,
            patch.object(commands, "safe_reply_text", new_callable=AsyncMock) as reply,
            patch.object(commands, "_can_manage_session", new_callable=AsyncMock) as manage,
            patch.object(debounce, "cancel_chat") as cancel,
        ):
            await commands.handle_summary_command(message)
            refresh.assert_awaited_once_with(-100)
            reply.assert_awaited_once_with(message, "本群摘要")
            manage.assert_not_awaited()
            cancel.assert_not_called()

    async def test_private_chat_uses_its_own_summary(self):
        message = self.message(private=True)
        with (
            patch.object(context_store, "force_refresh_summary_async", new_callable=AsyncMock, return_value="私聊摘要") as refresh,
            patch.object(commands, "safe_reply_text", new_callable=AsyncMock),
        ):
            await commands.handle_summary_command(message)
            refresh.assert_awaited_once_with(42)

    async def test_empty_summary_keeps_backup_message(self):
        message = self.message()
        with (
            patch.object(context_store, "force_refresh_summary_async", new_callable=AsyncMock, return_value=""),
            patch.object(commands, "safe_reply_text", new_callable=AsyncMock) as reply,
        ):
            await commands.handle_summary_command(message)
            reply.assert_awaited_once_with(message, "当前群组暂无聊天摘要。")

    async def test_failure_keeps_backup_message_without_traceback(self):
        message = self.message()
        error = RuntimeError("Traceback: private server details")
        with (
            patch.object(context_store, "force_refresh_summary_async", new_callable=AsyncMock, side_effect=error),
            patch.object(commands, "safe_reply_text", new_callable=AsyncMock) as reply,
            patch.object(commands, "report_exception") as report,
        ):
            await commands.handle_summary_command(message)
            reply.assert_awaited_once_with(message, "获取摘要失败，请稍后再试。")
            report.assert_called_once_with(error)

    async def test_extra_arguments_return_usage_without_calling_model(self):
        message = self.message("/summary extra")
        with (
            patch.object(context_store, "force_refresh_summary_async", new_callable=AsyncMock) as refresh,
            patch.object(commands, "safe_reply_text", new_callable=AsyncMock) as reply,
        ):
            await commands.handle_summary_command(message)
            refresh.assert_not_awaited()
            reply.assert_awaited_once_with(message, "用法：/summary")


if __name__ == "__main__":
    unittest.main()
