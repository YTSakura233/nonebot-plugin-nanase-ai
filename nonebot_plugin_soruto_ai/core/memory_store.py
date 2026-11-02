import re
from datetime import datetime
from typing import TypedDict

from .util import report_exception
from .db import get_db_connection_async


VALID_CATEGORIES = {"preference", "relation", "event", "nickname", "trait", "knowledge", "other"}
ALLOWED_ACTIONS = {"add", "delete", "update"}
MAX_FACT_LEN = 240
MAX_FACTS_PER_SCOPE = 200      # 硬上限，溢出按 last_seen_at ASC 淘汰
MAX_FACTS_FETCH = 100          # 单次检索拉取上限
TOP_K_INJECT = 10              # 用户事实：在动态尾巴里按当前消息打分，不影响前缀缓存
STABLE_GROUP_FACTS_LIMIT = 20  # 群事实前缀：按 id 稳定排序（不用 hit_count，避免每次回复打乱前缀）
KNOWLEDGE_TOP_K = 5            # 当前消息命中的圈内知识，单独打给模型
KNOWLEDGE_MIN_QUERY_LEN = 4
KNOWLEDGE_MIN_OVERLAP = 2
KNOWLEDGE_SCORE_THRESHOLD = 0.22
# 问的是现状，而事实自己标明只属于过去。版本是否还对得上现状由策略阶段判断，这里不猜。
_PRESENT_QUERY_RE = re.compile(
    r"现在|目前|当前|如今|最新|现况|现状|有没有|还有没有|还在|还能|是否还|是不是还"
)
_ASKING_ABOUT_PAST_RE = re.compile(
    r"以前|之前|从前|当初|那时|那时候|当时|曾经|旧版|老版|历史|过去|去年|上次|记得吗|还记得"
)
_PAST_ONLY_FACT_RE = re.compile(
    r"以前|之前|从前|当初|那时|那时候|当时|曾经|旧版|老版|那会|那会儿|早年|去年"
)
# 功能词/虚词。单独或成串重复都不能当作 knowledge 命中依据；专有词不在此列。
_KNOWLEDGE_STOPWORDS = frozenset({
    "一个", "一些", "一下", "一种", "这个", "那个", "这些", "那些", "什么", "怎么", "怎样",
    "为什么", "因为", "所以", "但是", "不过", "然后", "就是", "还是", "或者", "如果", "虽然",
    "可以", "不能", "没有", "不是", "以及", "而且", "并且", "已经", "正在", "觉得", "感觉",
    "知道", "其实", "确实", "真的", "可能", "应该", "需要", "时候", "东西", "问题", "情况",
    "我们", "你们", "他们", "她们", "自己", "别人", "大家", "今天", "现在", "然后", "还有",
    "一下", "这样", "那样", "这么", "那么", "这里", "那里", "哪里", "多少", "非常", "比较",
    "不要", "不用", "不会", "不能", "不可", "不想", "别的", "什么", "怎么", "如何",
    "好像", "突然", "一直", "一起", "出来", "进去", "上来", "下去", "起来", "的话", "来说",
    "关于", "对于", "通过", "进行", "使用", "看到", "听到", "觉得", "认为", "表示", "说明",
})
_KNOWLEDGE_STOP_CHARS = frozenset(
    "的了呢吧啊呀嘛哦喔嗯哈是在有和与或也就都还被把给对从向到不没要会能可"
)


class MemoryEvent(TypedDict, total=False):
    action: str              # add | delete
    scope: str               # user | group
    category: str
    fact: str


class FactRow(TypedDict):
    id: int
    scope_type: str
    scope_id: int
    category: str
    fact: str
    private: bool
    confidence: float
    hit_count: int
    last_seen_at: datetime


def _coerce_bool(v: object) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "y", "是")
    return False


def _normalize_event(ev: object, default_user_id: int, chat_id: int) -> tuple[str, str, int, str, str, str, bool] | None:
    """返回 (action, scope_type, scope_id, category, fact, old_fact, private)；非法返回 None。
    对于 add/delete，old_fact 为空字符串；对于 update，old_fact 为要替换的旧事实。
    private=True 表示该事实"知道但不要主动在别处/公开场合说出来"。"""
    if not isinstance(ev, dict):
        return None
    action = str(ev.get("action", "")).strip().lower()
    if action not in ALLOWED_ACTIONS:
        return None
    scope = str(ev.get("scope", "user")).strip().lower()
    scope_type = "group" if scope == "group" else "user"
    scope_id = chat_id if scope_type == "group" else default_user_id
    category = str(ev.get("category", "other")).strip().lower()
    if category not in VALID_CATEGORIES:
        category = "other"
    fact = str(ev.get("fact", "")).strip()
    if not fact:
        return None
    fact = fact[:MAX_FACT_LEN]
    private = _coerce_bool(ev.get("private", False))
    old_fact = ""
    if action == "update":
        old_fact = str(ev.get("old_fact", "")).strip()
        if not old_fact:
            return None
        old_fact = old_fact[:MAX_FACT_LEN]
    return (action, scope_type, scope_id, category, fact, old_fact, private)


async def apply_memory_events_async(events: list[dict], user_id: int, chat_id: int) -> None:
    if not events:
        return
    try:
        async with get_db_connection_async() as conn:
            async with conn.cursor() as cur:
                for raw in events:
                    norm = _normalize_event(raw, user_id, chat_id)
                    if not norm:
                        continue
                    action, scope_type, scope_id, category, fact, old_fact, private = norm
                    if action == "add":
                        # 完全一致则 bump hit_count
                        await cur.execute(
                            """
                            SELECT id FROM soruto_nb_memory_facts
                            WHERE scope_type = %s AND scope_id = %s AND fact = %s LIMIT 1
                            """,
                            (scope_type, scope_id, fact),
                        )
                        existing = await cur.fetchone()
                        if existing:
                            await cur.execute(
                                """
                                UPDATE soruto_nb_memory_facts
                                SET hit_count = hit_count + 1, last_seen_at = CURRENT_TIMESTAMP,
                                    private = GREATEST(private, %s)
                                WHERE id = %s
                                """,
                                (1 if private else 0, existing[0]),
                            )
                        else:
                            await cur.execute(
                                """
                                INSERT INTO soruto_nb_memory_facts
                                (scope_type, scope_id, category, fact, private)
                                VALUES (%s, %s, %s, %s, %s)
                                """,
                                (scope_type, scope_id, category, fact, 1 if private else 0),
                            )
                    elif action == "delete":
                        await cur.execute(
                            """
                            DELETE FROM soruto_nb_memory_facts
                            WHERE scope_type = %s AND scope_id = %s AND fact = %s
                            """,
                            (scope_type, scope_id, fact),
                        )
                    elif action == "update":
                        # 用 old_fact 模糊定位旧记录（LIKE匹配），替换为新 fact
                        await cur.execute(
                            """
                            SELECT id, fact FROM soruto_nb_memory_facts
                            WHERE scope_type = %s AND scope_id = %s AND fact LIKE %s
                            ORDER BY last_seen_at DESC LIMIT 1
                            """,
                            (scope_type, scope_id, f"%{old_fact}%"),
                        )
                        existing = await cur.fetchone()
                        if existing:
                            await cur.execute(
                                """
                                UPDATE soruto_nb_memory_facts
                                SET fact = %s, category = %s, private = GREATEST(private, %s), last_seen_at = CURRENT_TIMESTAMP
                                WHERE id = %s
                                """,
                                (fact, category, 1 if private else 0, existing[0]),
                            )
                        else:
                            # old_fact 匹配不到，直接新增修正后的事实
                            await cur.execute(
                                """
                                INSERT INTO soruto_nb_memory_facts
                                (scope_type, scope_id, category, fact, private)
                                VALUES (%s, %s, %s, %s, %s)
                                """,
                                (scope_type, scope_id, category, fact, 1 if private else 0),
                            )
                # 溢出淘汰：每个 scope 保留最近 MAX_FACTS_PER_SCOPE 条
                scopes = {(norm[1], norm[2]) for raw in events if (norm := _normalize_event(raw, user_id, chat_id))}
                for s_type, s_id in scopes:
                    await cur.execute(
                        "SELECT COUNT(*) FROM soruto_nb_memory_facts WHERE scope_type=%s AND scope_id=%s",
                        (s_type, s_id),
                    )
                    cnt_row = await cur.fetchone()
                    cnt = int(cnt_row[0]) if cnt_row else 0
                    if cnt > MAX_FACTS_PER_SCOPE:
                        excess = cnt - MAX_FACTS_PER_SCOPE
                        await cur.execute(
                            """
                            DELETE FROM soruto_nb_memory_facts
                            WHERE scope_type=%s AND scope_id=%s
                            ORDER BY hit_count ASC, last_seen_at ASC
                            LIMIT %s
                            """,
                            (s_type, s_id, excess),
                        )
            await conn.commit()
    except Exception as e:
        report_exception(e)


async def _fetch_facts_async(scope_type: str, scope_id: int) -> list[FactRow]:
    async with get_db_connection_async() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT id, scope_type, scope_id, category, fact, private, confidence, hit_count, last_seen_at
                FROM soruto_nb_memory_facts
                WHERE scope_type = %s AND scope_id = %s
                ORDER BY last_seen_at DESC, hit_count DESC
                LIMIT %s
                """,
                (scope_type, scope_id, MAX_FACTS_FETCH),
            )
            rows = await cur.fetchall()
    return [
        {
            "id": r[0], "scope_type": r[1], "scope_id": r[2],
            "category": r[3], "fact": r[4], "private": bool(r[5]),
            "confidence": float(r[6]),
            "hit_count": int(r[7]), "last_seen_at": r[8],
        }
        for r in rows
    ]


_MIN_CONTENT_RELEVANCE = 0.15  # 有 query 时低于此值视为内容无关，hit_count 不能单独入选


_VERSION_RE = re.compile(
    r"(?<![\d.])(?:v|ver(?:sion)?|版本)\s*(\d+(?:\.\d+){1,3})(?![\d.])"
    r"|(?<![\d.])(\d+\.\d{1,2})(?![\d.])",
    re.IGNORECASE,
)


def versions_in_text(text: str) -> list[str]:
    """当前说法里点明的版本号。策略阶段用来对照记忆是不是还对得上现状。

    带「版本 / v」的多段号都算。不带标记时只收末段不超过两位的号，
    避免把 2026.10.16 这类日期当成版本。
    """
    found: list[str] = []
    for match in _VERSION_RE.finditer(text or ""):
        found.append(next(group for group in match.groups() if group))
    return list(dict.fromkeys(found))


def fact_is_stale_for_query(query: str, fact: str) -> bool:
    """问现状时，丢掉自己标明只属于过去的事实。

    对方在问以前，或这条事实同时写了现在怎样，则保留。没写「以前」的旧版本
    （例如记忆停在 1.53、问题在问 1.56）这里无法判断，交给策略阶段。
    """
    q = query or ""
    f = fact or ""
    if not q.strip() or not f.strip():
        return False
    if not _PRESENT_QUERY_RE.search(q) or _ASKING_ABOUT_PAST_RE.search(q):
        return False
    return _PAST_ONLY_FACT_RE.search(f) is not None and not _PRESENT_QUERY_RE.search(f)


def _content_relevance(fact: str, query: str) -> float:
    """当前消息与一条事实的内容相关度。不含 hit_count。"""
    query_l = query.lower().strip()
    fact_l = fact.lower().strip()
    if not query_l or not fact_l:
        return 0.0
    if fact_l in query_l or query_l in fact_l:
        return 1.0
    grams = {query_l[i:i + 2] for i in range(len(query_l) - 1)}
    if not grams:
        return 1.0 if query_l in fact_l else 0.0
    hits = sum(1 for g in grams if g in fact_l)
    return hits / len(grams)


def _score(fact: str, query: str, hit_count: int) -> float:
    """有 query 时必须先有内容相关才入选。返回值不含 hit_count，避免高频压过更相关的事实。
    空 query（/ai 状态）返回 0，由调用方按最近/命中列出。"""
    del hit_count  # 频率只在 _rank_facts 的同分排序里使用
    if not (query or "").strip():
        return 0.0
    base = _content_relevance(fact, query)
    if base < _MIN_CONTENT_RELEVANCE:
        return 0.0
    return base


def _cjk_pieces(tok: str) -> list[str]:
    """按单字虚词和双字功能词切开，只留连续专名片段。"""
    pieces: list[str] = []
    buf = ""
    i = 0
    while i < len(tok):
        if tok[i] in _KNOWLEDGE_STOP_CHARS:
            if len(buf) >= 2:
                pieces.append(buf)
            buf = ""
            i += 1
            continue
        pair = tok[i:i + 2]
        if pair in _KNOWLEDGE_STOPWORDS:
            if len(buf) >= 2:
                pieces.append(buf)
            buf = ""
            i += 2
            continue
        buf += tok[i]
        i += 1
    if len(buf) >= 2:
        pieces.append(buf)
    return [p for p in pieces if p not in _KNOWLEDGE_STOPWORDS]


def _distinctive_tokens(text: str) -> set[str]:
    """专有词与去掉虚词后的连续片段。功能词重复不能当作整条 knowledge 的命中依据。"""
    raw = re.findall(r"[a-z0-9][a-z0-9_\-]{1,}|[぀-ヿ]{2,}|[一-鿿]{2,}", text.lower())
    tokens: set[str] = set()
    for tok in raw:
        if tok in _KNOWLEDGE_STOPWORDS:
            continue
        if re.fullmatch(r"[一-鿿]+", tok):
            pieces = _cjk_pieces(tok)
            if not pieces:
                continue
            tokens.update(pieces)
            # 整段本身不含虚词时保留，方便「舞萌科技」这类专名整段命中
            if pieces == [tok]:
                tokens.add(tok)
        else:
            tokens.add(tok)
    return tokens


def _knowledge_relevance(fact: str, query: str) -> float:
    """当前消息与一条 knowledge 的相关度。

    不做近义词展开。去掉虚词后：整句包含、一个不少于 4 字的相同专名、
    或至少两个相同片段，才算命中。单个功能词或任意 4 字窗不再抬到 0.55。
    """
    q = query.lower().strip()
    f = fact.lower().strip()
    if len(q) < KNOWLEDGE_MIN_QUERY_LEN or len(f) < 2:
        return 0.0
    if f in q or q in f:
        return 1.0
    q_tokens = _distinctive_tokens(q)
    f_tokens = _distinctive_tokens(f)
    if not q_tokens or not f_tokens:
        return 0.0
    shared = set(q_tokens & f_tokens)
    for piece in q_tokens:
        if len(piece) >= 4 and any(piece in fact_piece for fact_piece in f_tokens):
            shared.add(piece)
    if not shared:
        return 0.0
    if not (len(shared) >= KNOWLEDGE_MIN_OVERLAP or any(len(piece) >= 4 for piece in shared)):
        return 0.0
    recall = len(shared) / len(f_tokens)
    return max(KNOWLEDGE_SCORE_THRESHOLD, min(0.95, 0.45 + 0.5 * recall))


async def fetch_stable_group_facts_async(
    chat_id: int, limit: int = STABLE_GROUP_FACTS_LIMIT
) -> tuple[list[str], list[int]]:
    """群级事实按 id 升序，不随当前消息打分，保证 prompt 前缀可缓存。"""
    try:
        async with get_db_connection_async() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT id, fact, private FROM soruto_nb_memory_facts
                    WHERE scope_type = 'group' AND scope_id = %s
                    ORDER BY id DESC
                    LIMIT %s
                    """,
                    (chat_id, limit),
                )
                rows = await cur.fetchall()
    except Exception as e:
        report_exception(e)
        return ([], [])
    rows = list(reversed(rows))
    texts: list[str] = []
    ids: list[int] = []
    for r in rows:
        ids.append(int(r[0]))
        fact = r[1]
        texts.append(f"（🔒勿外传）{fact}" if r[2] else fact)
    return (texts, ids)


def _render_fact(f: FactRow) -> str:
    # private 事实加锁标记，提示模型"知道但不要主动在别处/公开说出去"
    return f"（🔒勿外传）{f['fact']}" if f.get("private") else f["fact"]


def _eligible(facts: list[FactRow], allow_private: bool) -> list[FactRow]:
    """群聊公共生成默认不带 private。allow_private=True 时保留（私聊、/ai 状态）。"""
    if allow_private:
        return facts
    return [f for f in facts if not f.get("private")]


def _rank_facts(facts: list[FactRow], query: str, top_k: int) -> list[FactRow]:
    """空 query：按最近看到、其次 hit_count 列出（状态展示）。
    有 query：内容不相关的事实即使 hit_count 很高也不入选；频率只打平内容分。"""
    q = (query or "").strip()
    if not q:
        ordered = sorted(facts, key=lambda f: (f["last_seen_at"], f["hit_count"], int(f["id"])), reverse=True)
        return ordered[:top_k]
    facts = [f for f in facts if not fact_is_stale_for_query(q, f["fact"])]
    scored = [(f, _score(f["fact"], q, f["hit_count"])) for f in facts]
    scored = [(f, s) for f, s in scored if s > 0]
    # 内容分优先；只有相关度相同才用 hit_count，再按 id 稳定打平
    scored.sort(key=lambda x: (-x[1], -x[0]["hit_count"], -int(x[0]["id"])))
    return [f for f, _ in scored[:top_k]]


async def retrieve_relevant_knowledge_async(
    chat_id: int, query: str, top_k: int = KNOWLEDGE_TOP_K,
    allow_private: bool = False,
) -> tuple[list[str], list[int]]:
    """群组 knowledge 里与当前消息对得上的条目。只看 group：这是静默学习的「下次懂行」路径，
    不用 user 私密知识去抬群聊开口欲，以免把私下内容带到群里。
    allow_private 默认 False：标了 private 的群知识不进入公共生成。"""
    if not query or len(query.strip()) < KNOWLEDGE_MIN_QUERY_LEN:
        return ([], [])
    try:
        async with get_db_connection_async() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT id, fact, private, hit_count FROM soruto_nb_memory_facts
                    WHERE category = 'knowledge' AND scope_type = 'group' AND scope_id = %s
                    ORDER BY last_seen_at DESC, hit_count DESC
                    LIMIT %s
                    """,
                    (chat_id, MAX_FACTS_FETCH),
                )
                rows = await cur.fetchall()
    except Exception as e:
        report_exception(e)
        return ([], [])

    scored: list[tuple[float, int, int, str, bool]] = []
    for r in rows:
        private = bool(r[2])
        if private and not allow_private:
            continue
        fact = r[1] or ""
        if fact_is_stale_for_query(query, fact):
            continue
        score = _knowledge_relevance(fact, query)
        if score >= KNOWLEDGE_SCORE_THRESHOLD:
            scored.append((score, int(r[3] or 0), int(r[0]), fact, private))
    # 相关度优先；同等相关才看 hit_count
    scored.sort(key=lambda x: (-x[0], -x[1], -x[2]))
    top = scored[:top_k]
    texts = [f"（🔒勿外传）{row[3]}" if row[4] else row[3] for row in top]
    ids = [row[2] for row in top]
    return (texts, ids)


async def retrieve_relevant_group_facts_async(
    chat_id: int, query: str, top_k: int = TOP_K_INJECT,
    allow_private: bool = False,
) -> tuple[list[str], list[int]]:
    """与当前消息相关的群事实。有 query 时不相关的不注入；不再为前缀缓存塞入全部稳定群事实。
    allow_private 默认 False：群 private 不进入公共生成。空 query 返回空（状态展示走用户事实）。"""
    if not (query or "").strip():
        return ([], [])
    try:
        group_facts = await _fetch_facts_async("group", chat_id)
    except Exception as e:
        report_exception(e)
        return ([], [])
    top = _rank_facts(_eligible(group_facts, allow_private), query, top_k)
    return ([_render_fact(f) for f in top], [f["id"] for f in top])


async def retrieve_relevant_facts_async(
    user_id: int, chat_id: int, query: str, top_k: int = TOP_K_INJECT,
    include_group: bool = True,
    allow_private: bool = True,
) -> tuple[list[str], list[str], list[int]]:
    """返回 (user_facts_texts, group_facts_texts, hit_fact_ids)。

    allow_private 默认 True，兼容 /ai 状态（空 query 仍列出自己的事实，含 private）。
    群聊公共生成应传 allow_private=False：用户 private 与群 private 都不进入候选。
    有 query 时，内容不相关的事实不能仅凭 hit_count 入选。
    """
    try:
        user_facts = await _fetch_facts_async("user", user_id)
        group_facts = await _fetch_facts_async("group", chat_id) if include_group else []
    except Exception as e:
        report_exception(e)
        return ([], [], [])

    top_user = _rank_facts(_eligible(user_facts, allow_private), query, top_k)
    top_group = _rank_facts(_eligible(group_facts, allow_private), query, top_k) if include_group else []
    ids = [f["id"] for f in top_user] + [f["id"] for f in top_group]
    return (
        [_render_fact(f) for f in top_user],
        [_render_fact(f) for f in top_group],
        ids,
    )


async def bump_hit_count_async(fact_ids: list[int]) -> None:
    if not fact_ids:
        return
    try:
        placeholders = ",".join(["%s"] * len(fact_ids))
        async with get_db_connection_async() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"""
                    UPDATE soruto_nb_memory_facts
                    SET hit_count = hit_count + 1, last_seen_at = CURRENT_TIMESTAMP
                    WHERE id IN ({placeholders})
                    """,
                    tuple(fact_ids),
                )
            await conn.commit()
    except Exception as e:
        report_exception(e)
