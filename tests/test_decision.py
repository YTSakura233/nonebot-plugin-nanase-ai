import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from nonebot_plugin_soruto_ai.core import decision


class ReplyPolicyTests(unittest.IsolatedAsyncioTestCase):
    def messages(self, **fields):
        dynamic = {"name": "群友", "message": "大家正在聊天", "is_private": False,
                   "is_at": False, "is_reply_to_you": False, "is_continuation": False,
                   "is_breakthrough": False, "ai_off": False, "memory_candidates": []}
        dynamic.update(fields)
        return decision._build_ai_messages("", [], dynamic)

    async def test_unstructured_policy_cannot_become_unsolicited_reply(self):
        with (
            patch.object(decision.llm, "chat_text_async", new_callable=AsyncMock, return_value="这种事是违法的。到此为止。"),
            patch.object(decision.llm, "agent_text_async", new_callable=AsyncMock, return_value="这种事是违法的。到此为止。") as generate,
            patch.object(decision, "report_exception"),
        ):
            result = await decision.call_main_model_async(self.messages(), None, request_context=None, session_id=None)
            self.assertTrue(result is None or not result["message"])
            generate.assert_not_awaited()

    async def test_casual_decline_plan_stays_silent(self):
        plan = {"should_reply": True, "reply_kind": "decline", "route": "simple", "memory_indices": []}
        with (
            patch.object(decision.llm, "chat_text_async", new_callable=AsyncMock, return_value=json.dumps(plan)),
            patch.object(decision.llm, "agent_text_async", new_callable=AsyncMock, return_value="到此为止。") as generate,
        ):
            result = await decision.call_main_model_async(self.messages(), None, request_context=None, session_id=None)
            assert result is not None
            self.assertEqual(result["message"], "")
            generate.assert_not_awaited()

    async def test_complex_answer_only_receives_selected_memory(self):
        plan = {"should_reply": True, "reply_kind": "answer", "route": "complex", "memory_indices": [0],
                "affinity_delta": 0, "memory_events": []}
        with (
            patch.object(decision.llm, "chat_text_async", new_callable=AsyncMock, return_value=json.dumps(plan)),
            patch.object(decision.llm, "agent_text_async", new_callable=AsyncMock, return_value="查证后的答案") as generate,
        ):
            result = await decision.call_main_model_async(
                self.messages(is_private=True, memory_candidates=["相关事实", "不相关旧记忆"]),
                None, request_context=object(), session_id="test", use_tools=True,
            )
            assert result is not None and generate.await_args is not None
            self.assertEqual(result["message"], "查证后的答案")
            self.assertEqual(generate.await_args.kwargs["purpose"], "complex")
            transmitted = generate.await_args.args[1] + str(generate.await_args.kwargs.get("contexts", []))
            self.assertIn("相关事实", transmitted)
            self.assertNotIn("不相关旧记忆", transmitted)
            self.assertTrue(generate.await_args.kwargs["use_tools"])

    async def test_simple_casual_search_uses_short_tool_mode(self):
        plan = {"should_reply": True, "reply_kind": "answer", "route": "simple", "needs_tools": True, "memory_indices": []}
        with (
            patch.object(decision.llm, "chat_text_async", new_callable=AsyncMock, return_value=json.dumps(plan)),
            patch.object(decision.llm, "agent_text_async", new_callable=AsyncMock, return_value="搜到的结果") as generate,
        ):
            result = await decision.call_main_model_async(self.messages(), None, request_context=object(), session_id="group", use_tools=True)
            assert result is not None and generate.await_args is not None
            self.assertEqual(result["message"], "搜到的结果")
            self.assertEqual(generate.await_args.kwargs["purpose"], "simple")
            self.assertTrue(generate.await_args.kwargs["casual"])
            self.assertTrue(generate.await_args.kwargs["use_tools"])

    async def test_policy_uses_media_text_while_final_generation_gets_original_image(self):
        plan = {"should_reply": True, "reply_kind": "answer", "route": "simple", "memory_indices": []}
        with (
            patch.object(decision, "_image_data_uris", return_value=["data:image/png;base64,test"]),
            patch.object(decision.llm, "chat_text_async", new_callable=AsyncMock, return_value=json.dumps(plan)) as policy,
            patch.object(decision.llm, "agent_text_async", new_callable=AsyncMock, return_value="图片内容") as generate,
        ):
            await decision.call_main_model_async(self.messages(is_private=True), None, request_context=object(), session_id="private")
            assert policy.await_args is not None and generate.await_args is not None
            self.assertIsNone(policy.await_args.kwargs["image_urls"])
            self.assertEqual(generate.await_args.kwargs["purpose"], "complex")
            self.assertEqual(generate.await_args.kwargs["image_urls"], ["data:image/png;base64,test"])

    async def test_policy_sees_current_versions_beside_memory_candidates(self):
        plan = {"should_reply": True, "reply_kind": "answer", "route": "simple", "memory_indices": []}
        with (
            patch.object(decision.llm, "chat_text_async", new_callable=AsyncMock, return_value=json.dumps(plan)) as policy,
            patch.object(decision.llm, "agent_text_async", new_callable=AsyncMock, return_value="不知道喵"),
        ):
            await decision.call_main_model_async(
                self.messages(
                    message="舞萌DX目前版本是1.56，这个行为还在吗",
                    current_versions=["1.56"],
                    memory_candidates=["1.53 里这个判定走旧分支"],
                ),
                None, request_context=object(), session_id="group",
            )
            assert policy.await_args is not None
            payload = policy.await_args.args[0]
            self.assertIn("1.56", payload)
            self.assertIn("current_versions", payload)
            self.assertIn("版本不在其中", decision.SYSTEM_PROMPT)

    async def test_direct_decline_is_not_treated_as_outage(self):
        plan = {"should_reply": True, "reply_kind": "decline", "route": "simple", "memory_indices": []}
        with (
            patch.object(decision.llm, "chat_text_async", new_callable=AsyncMock, return_value=json.dumps(plan)),
            patch.object(decision.llm, "agent_text_async", new_callable=AsyncMock, return_value="这个请求我不能帮助。") as generate,
        ):
            result = await decision.call_main_model_async(self.messages(is_at=True), None, request_context=object(), session_id="test")
            assert result is not None
            self.assertEqual(result["message"], "这个请求我不能帮助。")
            self.assertEqual(generate.await_count, 1)


if __name__ == "__main__":
    unittest.main()
