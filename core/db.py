import asyncio
from contextlib import asynccontextmanager

import aiomysql

from . import config

_async_pool = None
_async_pool_lock = asyncio.Lock()


async def _get_async_pool():
    global _async_pool
    async with _async_pool_lock:
        if _async_pool is None or _async_pool.closed:
            cfg = config.SETTINGS
            _async_pool = await aiomysql.create_pool(
                host=cfg.soruto_db_host, port=cfg.soruto_db_port,
                user=cfg.soruto_db_user, password=cfg.soruto_db_password.get_secret_value(),
                db=cfg.soruto_db_name, minsize=1, maxsize=10,
                autocommit=False, charset='utf8mb4', connect_timeout=8,
                init_command="SET time_zone='+08:00'",
            )
    return _async_pool


@asynccontextmanager
async def get_db_connection_async():
    pool = await _get_async_pool()
    async with pool.acquire() as conn:
        try:
            yield conn
        finally:
            await conn.rollback()


async def close_async_pool():
    global _async_pool
    if _async_pool is not None:
        _async_pool.close()
        await _async_pool.wait_closed()
        _async_pool = None


async def ensure_user_async(user_id: int):
    async with get_db_connection_async() as conn:
        async with conn.cursor() as cur:
            await cur.execute('INSERT IGNORE INTO soruto_nb_users (qq_id) VALUES (%s)', (user_id,))
        await conn.commit()


async def is_user_known_async(user_id: int) -> bool:
    if user_id in config.SETTINGS.soruto_banned_users:
        return False
    async with get_db_connection_async() as conn:
        async with conn.cursor() as cur:
            await cur.execute('SELECT is_banned FROM soruto_nb_users WHERE qq_id=%s', (user_id,))
            row = await cur.fetchone()
    return row is not None and not row[0]
