import hashlib
from types import SimpleNamespace

from nonebot.adapters.onebot.v11 import Message as OBMessage, MessageSegment
from nonebot.adapters.onebot.v11.exception import ActionFailed

from ..models import Chat, Media, Message, ReferencedMessage, Update, User


def resolve_send_bot(message, fallback=None):
    getter = getattr(message, 'get_bot', None)
    return getter() if callable(getter) else fallback


def is_uninitialized_error(error):
    return False


class QQTransport:
    def __init__(self, bot):
        self.bot = bot
        self.self_id = str(bot.self_id)

    def _target(self, chat_id):
        bot_id, kind, target = str(chat_id).split(':')
        if bot_id != self.self_id or kind not in {'private', 'group'}:
            raise ValueError('session does not belong to this bot')
        return {'message_type': kind, ('group_id' if kind == 'group' else 'user_id'): int(target)}

    async def send_message(self, chat_id, text, reply_to=None, **kwargs):
        payload = OBMessage(MessageSegment.text(text))
        if reply_to is not None:
            payload = MessageSegment.reply(reply_to) + payload
        try:
            return await self.bot.send_msg(**self._target(chat_id), message=payload)
        except ActionFailed as error:
            detail = str(error.info).lower()
            if reply_to is None or not any(s in detail for s in ('reply not found', 'message to reply', 'replied message', '回复消息不存在')):
                raise
            return await self.bot.send_msg(**self._target(chat_id), message=OBMessage(MessageSegment.text(text)))

    async def send_chat_action(self, *_args):
        return None  # OneBot V11 has no typing status API.

    async def get_chat_member(self, chat_id, user_id):
        target = self._target(chat_id)
        result = await self.bot.get_group_member_info(group_id=target['group_id'], user_id=user_id, no_cache=True)
        return SimpleNamespace(status='creator' if result.get('role') == 'owner' else result.get('role'))


def from_event(bot, event) -> Update:
    group_id = getattr(event, 'group_id', None)
    kind = 'group' if group_id is not None else 'private'
    key = f'{bot.self_id}:{kind}:{group_id if group_id is not None else event.user_id}'
    sender = event.sender
    user = User(event.user_id, sender.card or sender.nickname or str(event.user_id))
    quoted = getattr(event, 'reply', None)
    reply = None
    if quoted is not None and quoted.sender.user_id is not None:
        reply = ReferencedMessage(quoted.message_id, User(quoted.sender.user_id, quoted.sender.nickname or ''))
    original = event.original_message
    mentioned = any(s.type == 'at' and str(s.data.get('qq')) == str(bot.self_id) for s in original)
    media = []
    for segment in original:
        if segment.type == 'image':
            url = str(segment.data.get('url') or '')
            identity = str(segment.data.get('file') or url)
            digest = hashlib.sha256(f'{bot.self_id}:{identity}'.encode()).hexdigest()
            media.append(Media(digest, url, 'photo', source_file=str(segment.data.get('file') or '')))
        elif segment.type == 'record':
            media.append(Media('', '', 'voice'))
        elif segment.type == 'face':
            media.append(Media('', '', 'face'))
    from datetime import datetime, timezone
    message = Message(
        Chat(key, kind), user, event.message_id, event.get_plaintext(), QQTransport(bot),
        date=datetime.fromtimestamp(event.time, timezone.utc), reply_to_message=reply,
        media=media, mentioned_bot=mentioned, sender_chat=getattr(event, 'anonymous', None),
    )
    return Update(message)
