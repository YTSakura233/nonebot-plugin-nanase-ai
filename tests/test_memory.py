"""记忆检索的确定性测试。伪造数据库游标，不连接 MySQL、Telegram 或模型。"""
import sys
import unittest
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from nonebot_plugin_soruto_ai.core import memory_store


def _row(fact_id, scope_type, scope_id, category, fact, private, hit_count, seen):
    return {
        "id": fact_id,
        "scope_type": scope_type,
        "scope_id": scope_id,
        "category": category,
        "fact": fact,
        "private": private,
        "confidence": 1.0,
        "hit_count": hit_count,
        "last_seen_at": seen,
    }


class _Cursor:
    def __init__(self, script):
        self._script = script
        self._rows = []
        self.queries = []

    async def execute(self, sql, params=None):
        self.queries.append((sql, params))
        self._rows = list(self._script(sql, params))

    async def fetchall(self):
        return self._rows

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Conn:
    def __init__(self, script):
        self.cursor_obj = _Cursor(script)

    def cursor(self):
        return self.cursor_obj

    async def commit(self):
        return None


def _patch_db(script):
    conn = _Conn(script)

    @asynccontextmanager
    async def fake_conn():
        yield conn

    return patch.object(memory_store, "get_db_connection_async", fake_conn), conn


class MemoryRetrievalTests(unittest.IsolatedAsyncioTestCase):
    def _store(self):
        t0 = datetime(2026, 8, 1, tzinfo=timezone.utc)
        t1 = datetime(2026, 8, 2, tzinfo=timezone.utc)
        t2 = datetime(2026, 8, 3, tzinfo=timezone.utc)
        user = [
            _row(1, "user", 42, "preference", "喜欢鲑鱼三明治", False, 1, t1),
            _row(2, "user", 42, "other", "养了一只叫团子的猫", False, 500, t0),
            _row(3, "user", 42, "event", "私聊说过不想让群里知道自己换了工作", True, 3, t2),
        ]
        group = [
            _row(11, "group", -100, "knowledge", "店里的 IO 板要先刷 AMEX 固件再接线", False, 2, t1),
            _row(12, "group", -100, "knowledge", "然后就是这样可以了，大家觉得没有问题", False, 80, t2),
            _row(13, "group", -100, "event", "群里约定周五一起试新菜单", False, 4, t0),
            _row(14, "group", -100, "knowledge", "某人私下提过备用固件密码不要外传", True, 9, t2),
            _row(15, "group", -100, "other", "群里有人养了三只仓鼠", False, 900, t2),
        ]
        return user, group

    def _script(self, user, group):
        def script(sql, params):
            scope = params[0]
            rows = user if scope == "user" else group
            # knowledge 查询按 (id, fact, private, hit_count)
            if "category = 'knowledge'" in sql:
                return [(r["id"], r["fact"], int(r["private"]), r["hit_count"]) for r in rows]
            return [
                (
                    r["id"], r["scope_type"], r["scope_id"], r["category"], r["fact"],
                    int(r["private"]), r["confidence"], r["hit_count"], r["last_seen_at"],
                )
                for r in rows
            ]
        return script

    async def test_high_hit_count_unrelated_fact_is_not_injected(self):
        user, group = self._store()
        db, _conn = _patch_db(self._script(user, group))
        with db:
            texts, group_texts, ids = await memory_store.retrieve_relevant_facts_async(
                42, -100, "今天想做鲑鱼三明治", include_group=True, allow_private=False,
            )
        self.assertEqual(texts, ["喜欢鲑鱼三明治"])
        self.assertNotIn(2, ids)
        self.assertNotIn(15, ids)
        self.assertFalse(any("仓鼠" in t or "团子" in t for t in texts + group_texts))

    async def test_hit_count_only_breaks_equal_relevance(self):
        t = datetime(2026, 8, 1, tzinfo=timezone.utc)
        user = [
            _row(1, "user", 42, "preference", "喜欢肉桂卷", False, 1, t),
            _row(2, "user", 42, "preference", "喜欢肉桂卷", False, 40, t),
        ]
        # 两条内容完全相同，相关度相同，高 hit_count 排前
        user[1]["fact"] = "喜欢肉桂卷配咖啡"
        db, _conn = _patch_db(self._script(user, []))
        with db:
            texts, _, ids = await memory_store.retrieve_relevant_facts_async(
                42, -100, "肉桂卷", include_group=False,
            )
        self.assertEqual(ids[0], 2)
        self.assertEqual(set(ids), {1, 2})
        self.assertTrue(texts[0].startswith("喜欢肉桂卷"))

    async def test_empty_query_status_lists_own_facts_including_private(self):
        user, group = self._store()
        db, _conn = _patch_db(self._script(user, group))
        with db:
            texts, group_texts, ids = await memory_store.retrieve_relevant_facts_async(
                42, -100, "", top_k=12,
            )
        self.assertEqual(len(texts), 3)
        self.assertIn("（🔒勿外传）私聊说过不想让群里知道自己换了工作", texts)
        self.assertIn(3, ids)
        # 空 query 按 last_seen_at 新到旧，private 那条最新
        self.assertEqual(texts[0], "（🔒勿外传）私聊说过不想让群里知道自己换了工作")
        self.assertTrue(group_texts)

    async def test_public_generation_excludes_private_user_and_group(self):
        user, group = self._store()
        db, _conn = _patch_db(self._script(user, group))
        with db:
            texts, group_texts, ids = await memory_store.retrieve_relevant_facts_async(
                42, -100, "换了工作之后还提过固件密码和鲑鱼三明治",
                include_group=True, allow_private=False,
            )
        blob = "\n".join(texts + group_texts)
        self.assertNotIn("换了工作", blob)
        self.assertNotIn("固件密码", blob)
        self.assertNotIn(3, ids)
        self.assertNotIn(14, ids)
        self.assertIn("喜欢鲑鱼三明治", texts)

    async def test_group_facts_query_returns_only_relevant_public(self):
        user, group = self._store()
        db, _conn = _patch_db(self._script(user, group))
        with db:
            texts, ids = await memory_store.retrieve_relevant_group_facts_async(
                -100, "周五的新菜单谁来试",
            )
            empty_texts, empty_ids = await memory_store.retrieve_relevant_group_facts_async(-100, "")
        self.assertEqual(texts, ["群里约定周五一起试新菜单"])
        self.assertEqual(ids, [13])
        self.assertEqual(empty_texts, [])
        self.assertEqual(empty_ids, [])

    async def test_relevant_knowledge_hits_proper_terms(self):
        _user, group = self._store()
        db, conn = _patch_db(self._script([], group))
        with db:
            texts, ids = await memory_store.retrieve_relevant_knowledge_async(
                -100, "这块 IO 板的 AMEX 固件要怎么刷",
            )
        self.assertEqual(ids, [11])
        self.assertEqual(texts, ["店里的 IO 板要先刷 AMEX 固件再接线"])
        sql = conn.cursor_obj.queries[0][0]
        self.assertIn("scope_type = 'group'", sql)
        self.assertIn("category = 'knowledge'", sql)

    async def test_function_word_repetition_does_not_hit_knowledge(self):
        _user, group = self._store()
        db, _conn = _patch_db(self._script([], group))
        query = "然后就是这样，然后就是这样，可以可以可以"
        # 旧的单片 4 字子串规则会把「然后就是」抬到 >=0.55；现在必须是 0
        self.assertEqual(memory_store._knowledge_relevance(group[1]["fact"], query), 0.0)
        self.assertEqual(
            memory_store._knowledge_relevance("店里的 IO 板要先刷 AMEX 固件再接线", "然后就是这样可以了"),
            0.0,
        )
        with db:
            texts, ids = await memory_store.retrieve_relevant_knowledge_async(-100, query)
        self.assertEqual(texts, [])
        self.assertEqual(ids, [])

    async def test_private_knowledge_excluded_unless_allow_private(self):
        _user, group = self._store()
        db, _conn = _patch_db(self._script([], group))
        query = "备用固件密码是什么不要外传"
        with db:
            hidden, hidden_ids = await memory_store.retrieve_relevant_knowledge_async(-100, query)
            shown, shown_ids = await memory_store.retrieve_relevant_knowledge_async(
                -100, query, allow_private=True,
            )
        self.assertEqual(hidden, [])
        self.assertEqual(hidden_ids, [])
        self.assertEqual(shown_ids, [14])
        self.assertTrue(shown[0].startswith("（🔒勿外传）"))

    async def test_present_question_drops_past_only_knowledge(self):
        t = datetime(2026, 8, 1, tzinfo=timezone.utc)
        group = [
            _row(21, "group", -100, "knowledge", "以前 CrackProof 基本只吃 Mono，il2cpp 不怎么管", False, 4, t),
            _row(22, "group", -100, "knowledge", "现在 CrackProof 仍只覆盖 Mono，il2cpp 还没管", False, 1, t),
            _row(23, "group", -100, "knowledge", "店里的 IO 板要先刷 AMEX 固件再接线", False, 2, t),
        ]
        db, _conn = _patch_db(self._script([], group))
        query = "话说现在 iOS 有没有免越狱巨魔砸壳的路子，想看看 iOS 侧的 CrackProof"
        with db:
            texts, ids = await memory_store.retrieve_relevant_knowledge_async(-100, query)
        self.assertNotIn(21, ids)
        self.assertNotIn("以前", "\n".join(texts))
        self.assertIn(22, ids)

    async def test_asking_about_the_past_keeps_past_facts(self):
        t = datetime(2026, 8, 1, tzinfo=timezone.utc)
        user = [
            _row(31, "user", 42, "knowledge", "以前 CrackProof 基本只吃 Mono", False, 1, t),
        ]
        db, _conn = _patch_db(self._script(user, []))
        with db:
            texts, _, ids = await memory_store.retrieve_relevant_facts_async(
                42, -100, "以前 CrackProof 是怎么处理 Mono 的", include_group=False,
            )
        self.assertEqual(ids, [31])
        self.assertIn("以前 CrackProof", texts[0])

    def test_version_markers_are_extracted_without_guessing_staleness(self):
        self.assertEqual(memory_store.versions_in_text("舞萌DX目前版本是1.56"), ["1.56"])
        self.assertEqual(memory_store.versions_in_text("v1.53 和 1.55 都测过"), ["1.53", "1.55"])
        self.assertEqual(memory_store.versions_in_text("版本2026.10.16"), ["2026.10.16"])
        self.assertEqual(memory_store.versions_in_text("2026.10.16 的记录"), [])
        # 1.53 没写「以前」，不能靠代码当成过时；交给策略对照 current_versions
        self.assertFalse(memory_store.fact_is_stale_for_query(
            "舞萌DX目前版本是1.56，这个行为还在吗", "1.53 里这个判定走旧分支",
        ))
        self.assertTrue(memory_store.fact_is_stale_for_query(
            "现在还有砸壳的路子吗", "以前 CrackProof 基本只吃 Mono",
        ))

    def test_prompt_keeps_persona_and_drops_forced_behaviors(self):
        path = Path(__file__).resolve().parents[1] / "nonebot_plugin_soruto_ai" / "system_prompt.md"
        text = path.read_text(encoding="utf-8")
        self.assertIn("ナナセ", text)
        self.assertIn("慵懒", text)
        self.assertIn("傲娇", text)
        self.assertIn("不是行为示例", text)
        self.assertIn("看到不等于必须使用或复述", text)
        self.assertIn("同一话题也不等于该用", text)
        self.assertIn("对不上现在的旧记忆就当没看见", text)
        self.assertIn("不是必须开口", text)
        self.assertIn("不要为了凑短硬压成大约 50 字", text)
        self.assertIn("被直接请求时按安全边界正常回应", text)
        self.assertNotIn("应当开口", text)
        self.assertNotIn("一般50字以内", text)


if __name__ == "__main__":
    unittest.main()
