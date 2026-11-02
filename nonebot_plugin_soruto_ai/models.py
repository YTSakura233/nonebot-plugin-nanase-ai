"""Platform-neutral turns; no Telegram or AstrBot objects cross this boundary."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class User:
    id: int
    full_name: str
    username: str = ''


@dataclass
class Chat:
    id: str
    type: str


@dataclass
class Media:
    file_id: str
    url: str
    type: str = 'photo'
    mime: str | None = None
    source_file: str = ''


@dataclass
class ReferencedMessage:
    message_id: int
    from_user: User


@dataclass
class Message:
    chat: Chat
    from_user: User
    message_id: int
    text: str
    native_bot: Any
    date: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    reply_to_message: ReferencedMessage | None = None
    media: list[Media] = field(default_factory=list)
    mentioned_bot: bool = False
    sender_chat: Any = None
    caption: str = ''

    @property
    def chat_id(self):
        return self.chat.id

    def get_bot(self):
        return self.native_bot

    async def reply_text(self, text: str, **kwargs):
        return await self.native_bot.send_message(self.chat_id, text, reply_to=self.message_id)


@dataclass
class Update:
    effective_message: Message

    @property
    def effective_chat(self):
        return self.effective_message.chat

    @property
    def effective_user(self):
        return self.effective_message.from_user
