"""Soruto commands and chat-bound confirmation flow for QQ."""
import time
from datetime import datetime, timezone, timedelta

from ..models import Message

from . import context_store, debounce, memory_store, transport
from .db import get_db_connection_async
from .decision import (
    get_user_ai_data_async,
    get_reset_cooldown_async,
    reset_user_ai_data_async,
    set_user_ai_enabled_async,
    update_user_favorability_async,
)
from .util import report_exception, safe_reply_text

# (chat_id, user_id) -> (action, monotonic_expire_ts)
_pending: dict[tuple[int, int], tuple[str, float]] = {}
_PENDING_TTL = 120.0

_TZ_UTC8 = timezone(timedelta(hours=8))


def _set_pending(chat_id: int, user_id: int, action: str) -> None:
    _pending[(chat_id, user_id)] = (action, time.monotonic() + _PENDING_TTL)


def _consume_pending(chat_id: int, user_id: int, action: str) -> bool:
    item = _pending.pop((chat_id, user_id), None)
    if not item:
        return False
    act, expire = item
    return act == action and time.monotonic() <= expire


async def _show_status(message: Message, user_id: int) -> None:
    data = await get_user_ai_data_async(user_id)
    facts, _, _ = await memory_store.retrieve_relevant_facts_async(
        user_id, message.chat_id, "", top_k=12, include_group=False,
        allow_private=message.chat.type == "private",
    )
    state = "开启" if data["is_enabled"] else "关闭"
    favorability = data['favorability']
    relation = next(label for minimum, label in (
        (61,'💕 很亲近'),(31,'💗 算是朋友'),(10,'🙂 有点兴趣'),
        (-9,'😐 中立'),(-49,'😒 不喜欢'),(-100,'💀 极度厌恶')) if favorability >= minimum)
    facts_text = "\n".join(f"• {fact}" for fact in facts) if facts else "（无）"
    await safe_reply_text(message,
        f"📊 你与ナナセ的关系\n回复状态：{state}\n好感度：{favorability}（{relation}）\n\n记忆事实：\n{facts_text}")


async def _check_reset_cooldown(user_id: int) -> str | None:
    """返回错误文案；可重置返回 None。"""
    cooldown = await get_reset_cooldown_async(user_id)
    now = datetime.now(_TZ_UTC8)
    if cooldown:
        if cooldown.tzinfo is None:
            cooldown = cooldown.replace(tzinfo=_TZ_UTC8)
        if cooldown > now:
            remaining = cooldown - now
            hours, remainder = divmod(int(remaining.total_seconds()), 3600)
            minutes = remainder // 60
            return f"❌ 重置冷却中，还需等待 {hours}小时{minutes}分钟 喵"
    return None


async def _do_breakthrough_off(message: Message, user_id: int) -> None:
    """突破状态下关闭回复：好感度 -100、记忆清空、3 天不可重置。"""
    next_reset_time = datetime.now(_TZ_UTC8) + timedelta(days=3)
    async with get_db_connection_async() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE soruto_ai
                SET favorability = -100, memory = NULL, isEnabled = 0, nextResetableTime = %s
                WHERE userId = %s
                """,
                (next_reset_time, user_id),
            )
            await cur.execute(
                "DELETE FROM soruto_nb_memory_facts WHERE scope_type='user' AND scope_id=%s",
                (user_id,),
            )
        await conn.commit()
    await safe_reply_text(
        message,
        "💔 ナナセ已经不想再理你了...\n\n"
        "好感度已降至最低，记忆已清空，3天内无法重置。",
    )


HELP_TEXT = """🍞 ナナセ AI
/ai — 查看个人状态
/ai help — 查看帮助
/summary — 查看当前聊天摘要
/ai compact — 压缩当前会话
/ai reset — 重置当前会话，保留长期记忆和好感度
/ai forget — 重置个人记忆及好感度，24小时冷却
/ai on — 开启定向回复
/ai off — 关闭定向回复；群内全天仍可闲聊
/ai breakthrough — 好感度100时申请突破

reset、forget、breakthrough 需先申请，再在同一聊天由本人2分钟内添加 confirm 确认。
突破后关闭回复也须 confirm，将清空个人记忆、好感度降至-100，3天内不能重置。
群聊 compact/reset 仅群主可用，私聊由本人操作。私密记忆仅私聊展示。
语音仅记录占位文字；图片使用视觉模型识别。"""

async def handle_help_command(message: Message) -> None:
    await safe_reply_text(message, HELP_TEXT, parse_mode="Markdown")


# summary // 查看本群聊天摘要
async def handle_summary_command(message: Message) -> None:
    if len((message.text or message.caption or "").split()) != 1:
        await safe_reply_text(message, "用法：/summary")
        return
    try:
        summary = await context_store.force_refresh_summary_async(message.chat_id)
        if not summary:
            await safe_reply_text(message, "当前群组暂无聊天摘要。")
            return
        await safe_reply_text(message, summary)
    except Exception as e:
        report_exception(e)
        await safe_reply_text(message, "获取摘要失败，请稍后再试。")


async def _can_manage_session(message: Message) -> bool:
    if message.chat.type == "private":
        return message.from_user is not None
    user = message.from_user
    if user is None or getattr(message, "sender_chat", None) is not None:
        await safe_reply_text(message, "请以群所有者的个人身份操作。")
        return False
    try:
        bot = transport.resolve_send_bot(message)
        if bot is None:
            raise RuntimeError("Telegram 客户端不可用")
        member = await bot.get_chat_member(chat_id=message.chat_id, user_id=user.id)
    except Exception as e:
        report_exception(e)
        await safe_reply_text(message, "身份验证失败，请稍后再试。")
        return False
    if member.status != "creator":
        await safe_reply_text(message, "仅群所有者可用。")
        return False
    return True


async def handle_ai_command(message: Message) -> None:
    """message 为 /ai 开头的 PTB Message。"""
    user = message.from_user
    if user is None:
        return
    text = message.text or message.caption or ""
    parts = text.split()
    # 去掉 /ai 本体（含 /ai@BotName 形式）
    args = parts[1:] if len(parts) > 1 else []

    try:
        if not args:
            await _show_status(message, user.id)
            return

        sub = args[0].lower()
        if sub == "help" and len(args) == 1:
            await handle_help_command(message)
            return

        # ai compact // 压缩当前聊天；群聊仅所有者可用，私聊允许当前用户
        # ai reset (confirm) // 重置当前会话，保留长期事实和好感度
        if sub in {"compact", "reset"}:
            if not await _can_manage_session(message):
                return
            if sub == "compact":
                if len(args) != 1:
                    await safe_reply_text(message, "用法：/ai compact（不接受其他参数）")
                    return
                debounce.cancel_chat(message.chat_id)
                compacted = await context_store.compact_session_async(message.chat_id)
                await safe_reply_text(message, "会话已压缩。" if compacted else
                                      "未压缩：无会话记录或模型暂不可用。")
                return
            if len(args) == 1:
                _set_pending(message.chat_id, user.id, "session_reset")
                await safe_reply_text(message,
                    "清空本聊天会话，保留长期记忆和好感度。\n"
                    "确认：/ai reset confirm（2分钟内）")
                return
            if len(args) == 2 and args[1].lower() == "confirm":
                if not _consume_pending(message.chat_id, user.id, "session_reset"):
                    await safe_reply_text(message, "确认已过期或不存在，请先发送 /ai reset。")
                    return
                debounce.cancel_chat(message.chat_id)
                await context_store.reset_session_async(message.chat_id)
                await safe_reply_text(message, "会话已重置。")
                return
            await safe_reply_text(message, "用法：/ai reset；确认时发送 /ai reset confirm")
            return

        if sub == "forget" and len(args) == 1:
            user_data = await get_user_ai_data_async(user.id)
            if user_data["favorability"] == 101:
                await safe_reply_text(message, "❌ 突破状态下无法重置喵...")
                return
            err = await _check_reset_cooldown(user.id)
            if err:
                await safe_reply_text(message, err)
                return
            _set_pending(message.chat_id, user.id, "forget")
            await safe_reply_text(
                message,
                "⚠️ 确定要重置吗？\n\n"
                "这将清空你与ナナセ的所有记忆和好感度，且重置后需要等待24小时才能再次重置。\n\n"
                "确认请在 2 分钟内发送：/ai forget confirm",
            )
            return

        if sub == "forget" and len(args) == 2 and args[1].lower() == "confirm":
            if not _consume_pending(message.chat_id, user.id, "forget"):
                await safe_reply_text(message, "❌ 没有待确认的重置请求（可能已过期），请先发送 /ai forget")
                return
            user_data = await get_user_ai_data_async(user.id)
            if user_data["favorability"] == 101:
                await safe_reply_text(message, "❌ 突破状态下无法重置喵...")
                return
            err = await _check_reset_cooldown(user.id)
            if err:
                await safe_reply_text(message, err)
                return
            await reset_user_ai_data_async(user.id)
            await safe_reply_text(message, "✅ 已重置你的好感度和记忆了喵~")
            return

        if sub == "on" and len(args) == 1:
            await set_user_ai_enabled_async(user.id, True)
            await safe_reply_text(message, "✅ 已开启 ナナセ ，喵喵~")
            return

        if sub == "off" and len(args) == 1:
            user_data = await get_user_ai_data_async(user.id)
            if user_data["favorability"] == 101:
                _set_pending(message.chat_id, user.id, "off_breakthrough")
                await safe_reply_text(
                    message,
                    "⚠️ 你真的要这样做吗？\n\n"
                    "在突破状态下关闭回复，ナナセ会感到非常受伤...\n"
                    "你的好感度将会降至最低，所有记忆都会被清空，并且在很长一段时间内无法重新开始。\n\n"
                    "这个决定无法撤回。确认请在 2 分钟内发送：/ai off confirm",
                )
                return
            await set_user_ai_enabled_async(user.id, False)
            await safe_reply_text(message, "✅ 已关闭 ナナセ 回复qwq")
            return

        if sub == "off" and len(args) == 2 and args[1].lower() == "confirm":
            if not _consume_pending(message.chat_id, user.id, "off_breakthrough"):
                await safe_reply_text(message, "❌ 没有待确认的关闭请求（可能已过期），请先发送 /ai off")
                return
            user_data = await get_user_ai_data_async(user.id)
            if user_data["favorability"] != 101:
                await safe_reply_text(message, "❌ 状态已变更，操作已取消")
                return
            await _do_breakthrough_off(message, user.id)
            return

        if sub == "breakthrough" and len(args) == 1:
            user_data = await get_user_ai_data_async(user.id)
            if user_data["favorability"] == 101:
                await safe_reply_text(message, "💕 你已经处于突破状态了喵~")
                return
            if user_data["favorability"] < 100:
                await safe_reply_text(
                    message,
                    f"❌ 好感度不足喵... 当前: {user_data['favorability']}/100",
                )
                return
            _set_pending(message.chat_id, user.id, "breakthrough")
            await safe_reply_text(
                message,
                "✨ 好感度已满！\n\n"
                "突破后，ナナセ会不再选择性回复消息，而是主动回应你的所有发言~\n\n"
                "但是请注意，如果在突破状态下选择关闭回复，ナナセ会非常伤心，"
                "好感度将降至最低、所有记忆都会被清空，并且无法在短时间内重新开始。\n\n"
                "确认请在 2 分钟内发送：/ai breakthrough confirm",
            )
            return

        if sub == "breakthrough" and len(args) == 2 and args[1].lower() == "confirm":
            if not _consume_pending(message.chat_id, user.id, "breakthrough"):
                await safe_reply_text(message, "❌ 没有待确认的突破请求（可能已过期），请先发送 /ai breakthrough")
                return
            user_data = await get_user_ai_data_async(user.id)
            if user_data["favorability"] != 100:
                await safe_reply_text(message, "❌ 好感度不足，无法突破喵")
                return
            await update_user_favorability_async(user.id, 101)
            await safe_reply_text(
                message,
                "💕 突破成功！\n\n从现在开始，ナナセ会主动回应你的所有消息~",
            )
            return

        await safe_reply_text(message, "参数错误。用 /ai help 查看用法。")
    except Exception as e:
        report_exception(e)
        await safe_reply_text(message, "执行失败，请稍后再试。")
