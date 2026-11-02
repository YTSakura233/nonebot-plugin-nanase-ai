from .db import get_db_connection_async

SCHEMA_STATEMENTS = [
    '''CREATE TABLE IF NOT EXISTS soruto_nb_users (
        qq_id BIGINT PRIMARY KEY, is_banned TINYINT NOT NULL DEFAULT 0
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4''',
    '''CREATE TABLE IF NOT EXISTS soruto_nb_ai (
        userId BIGINT PRIMARY KEY, favorability INT NOT NULL DEFAULT 20,
        memory TEXT NULL, isEnabled TINYINT NOT NULL DEFAULT 1,
        nextResetableTime DATETIME NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4''',
    '''CREATE TABLE IF NOT EXISTS soruto_nb_chat_context (
        seq BIGINT AUTO_INCREMENT PRIMARY KEY,
        chat_id VARCHAR(96) NOT NULL, chat_type VARCHAR(16) NOT NULL,
        role VARCHAR(16) NOT NULL, user_id BIGINT NULL, name VARCHAR(128) NOT NULL,
        text MEDIUMTEXT NOT NULL, message_id BIGINT NULL, reply_to_message_id BIGINT NULL,
        has_media TINYINT NOT NULL DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        KEY idx_chat_seq (chat_id,seq), KEY idx_user_seq (user_id,seq)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4''',
    '''CREATE TABLE IF NOT EXISTS soruto_nb_chat_summary (
        chat_id VARCHAR(96) PRIMARY KEY, summary TEXT, last_seq BIGINT NOT NULL DEFAULT 0,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4''',
    '''CREATE TABLE IF NOT EXISTS soruto_nb_memory_facts (
        id BIGINT AUTO_INCREMENT PRIMARY KEY, scope_type VARCHAR(16) NOT NULL,
        scope_id VARCHAR(96) NOT NULL, category VARCHAR(32) NOT NULL, fact VARCHAR(512) NOT NULL,
        private TINYINT NOT NULL DEFAULT 0, confidence FLOAT NOT NULL DEFAULT 0.5,
        hit_count INT NOT NULL DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        KEY idx_scope (scope_type,scope_id,last_seen_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4''',
    '''CREATE TABLE IF NOT EXISTS soruto_nb_media_description (
        file_id VARCHAR(160) PRIMARY KEY, media_type VARCHAR(24) NOT NULL,
        description TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4''',
    '''CREATE TABLE IF NOT EXISTS soruto_nb_knowledge (
        id BIGINT AUTO_INCREMENT PRIMARY KEY, collection_name VARCHAR(96) NOT NULL,
        source VARCHAR(512) NOT NULL, source_hash CHAR(64) NOT NULL, chunk_no INT NOT NULL,
        content MEDIUMTEXT NOT NULL, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        KEY idx_collection (collection_name), KEY idx_source (source_hash)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4''',
]


async def ensure_schema_async():
    async with get_db_connection_async() as conn:
        async with conn.cursor() as cur:
            for statement in SCHEMA_STATEMENTS:
                await cur.execute(statement)
        await conn.commit()
