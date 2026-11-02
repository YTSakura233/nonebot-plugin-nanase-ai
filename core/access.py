from datetime import datetime, timezone

from . import config, db

_startup_time = datetime.now(timezone.utc)


async def check_access_async(update):
    message = update.effective_message
    if message.date < _startup_time or message.sender_chat is not None:
        return False
    user_id = message.from_user.id
    if user_id in config.SETTINGS.soruto_banned_users:
        return False
    if message.chat.type == 'group':
        group_id = int(message.chat_id.rsplit(':', 1)[1])
        if group_id not in config.SETTINGS.soruto_allowed_groups:
            return False
        await db.ensure_user_async(user_id)
    return await db.is_user_known_async(user_id)
