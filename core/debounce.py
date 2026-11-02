import asyncio
from typing import Awaitable, Callable

from .util import report_exception

DEBOUNCE_SECONDS = 3.0


class _Pending:
    def __init__(self, fn: Callable[[], Awaitable[None]], priority: bool) -> None:
        self.fn = fn
        self.priority = priority
        self.task: asyncio.Task | None = None


# 显式提问按用户聚合，避免不同群员的两个问题互相覆盖。
_pending: dict[tuple[int, int | None], _Pending] = {}
_running: dict[int, set[asyncio.Task]] = {}
_revisions: dict[int, int] = {}
_epochs: dict[int, int] = {}


def current_epoch(chat_id: int) -> int:
    return _epochs.get(chat_id, 0)


def touch(chat_id: int) -> int:
    _revisions[chat_id] = current_revision(chat_id) + 1
    return _revisions[chat_id]


def current_revision(chat_id: int) -> int:
    return _revisions.get(chat_id, 0)


async def _run_after_delay(key: tuple[int, int | None], state: _Pending) -> None:
    try:
        await asyncio.sleep(DEBOUNCE_SECONDS)
        if _pending.get(key) is not state:
            return
        _pending.pop(key, None)
        task = asyncio.current_task()
        if task is not None:
            _running.setdefault(key[0], set()).add(task)
        try:
            await state.fn()
        finally:
            active = _running.get(key[0])
            if active is not None and task is not None:
                active.discard(task)
                if not active:
                    _running.pop(key[0], None)
    except asyncio.CancelledError:
        return
    except Exception as e:
        report_exception(e)
    finally:
        if _pending.get(key) is state:
            _pending.pop(key, None)


def schedule(chat_id: int, fn: Callable[[], Awaitable[None]], *, priority: bool = False,
             user_id: int | None = None) -> bool:
    """连续碎片共用三秒窗口；同一用户的补句保留先前显式提问的唤醒信号。"""
    key = (chat_id, user_id if priority else None)
    directed_key = (chat_id, user_id)
    directed = _pending.get(directed_key) if user_id is not None else None
    if not priority and directed is not None and directed.priority:
        key, fn, priority = directed_key, directed.fn, True
    from . import config
    active_count = len(_pending) + sum(len(tasks) for tasks in _running.values())
    if key not in _pending and active_count >= config.SETTINGS.soruto_max_pending_turns:
        return False
    if priority:
        general = _pending.pop((chat_id, None), None)
        if general and general.task:
            general.task.cancel()
    previous = _pending.pop(key, None)
    if previous and previous.task:
        previous.task.cancel()
    state = _Pending(fn, priority)
    _pending[key] = state
    state.task = asyncio.create_task(_run_after_delay(key, state))
    return True


def cancel_pending(chat_id: int) -> Callable[[], Awaitable[None]] | None:
    discarded = None
    for key in [k for k in _pending if k[0] == chat_id]:
        state = _pending.pop(key)
        discarded = state.fn
        if state.task:
            state.task.cancel()
    return discarded


def cancel_chat(chat_id: int) -> None:
    """会话操作前使旧结果失效，并取消等待和进行中的生成。"""
    _epochs[chat_id] = current_epoch(chat_id) + 1
    touch(chat_id)
    cancel_pending(chat_id)
    current = asyncio.current_task()
    for task in list(_running.get(chat_id, ())):
        if task is not current:
            task.cancel()


async def close() -> None:
    tasks = [s.task for s in _pending.values() if s.task is not None]
    tasks.extend(t for running in _running.values() for t in running)
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    _pending.clear()
    _running.clear()
    _revisions.clear()
    _epochs.clear()
