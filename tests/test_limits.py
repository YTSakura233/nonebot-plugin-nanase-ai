import asyncio
import sqlite3
from unittest.mock import AsyncMock, patch

from nonebot_plugin_soruto_ai.config import Config
from nonebot_plugin_soruto_ai.core import config, debounce, memory_store


async def test_pending_limit_preserves_an_existing_question():
    original = config.SETTINGS
    config.init(Config(soruto_max_pending_turns=1))
    try:
        with patch.object(debounce,'DEBOUNCE_SECONDS',10):
            assert debounce.schedule(1,AsyncMock(),priority=True,user_id=42)
            assert not debounce.schedule(2,AsyncMock(),priority=True,user_id=43)
            assert debounce.schedule(1,AsyncMock(),priority=True,user_id=42)
            assert len(debounce._pending)==1
    finally:
        await debounce.close()
        config.init(original)


async def test_memory_update_cannot_implicitly_publish_private_fact():
    connection=sqlite3.connect(':memory:')
    connection.create_function('GREATEST',2,max)
    connection.execute('''CREATE TABLE soruto_nb_memory_facts (
        id INTEGER PRIMARY KEY,scope_type TEXT,scope_id TEXT,category TEXT,fact TEXT,
        private INTEGER,hit_count INTEGER DEFAULT 0,last_seen_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
    connection.execute("INSERT INTO soruto_nb_memory_facts (scope_type,scope_id,category,fact,private) VALUES ('user','42','preference','旧秘密',1)")
    class Context:
        def __init__(self,value): self.value=value
        async def __aenter__(self): return self.value
        async def __aexit__(self,*args): return False
    class Cursor:
        async def execute(self,sql,args): self.cursor=connection.execute(sql.replace('%s','?'),args)
        async def fetchone(self): return self.cursor.fetchone()
    class Connection:
        def cursor(self): return Context(Cursor())
        async def commit(self): connection.commit()
    try:
        with patch.object(memory_store,'get_db_connection_async',return_value=Context(Connection())):
            await memory_store.apply_memory_events_async([
                {'action':'update','scope':'user','category':'preference','old_fact':'旧秘密','fact':'修正后的秘密','private':False}
            ],42,'999:private:42')
        assert connection.execute('SELECT fact,private FROM soruto_nb_memory_facts').fetchone()==('修正后的秘密',1)
    finally:
        connection.close()
