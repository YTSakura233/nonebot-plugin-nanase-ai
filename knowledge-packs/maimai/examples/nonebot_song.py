"""Optional local plugin example, separate from ナナセ AI; no player API."""
from pathlib import Path
import sys

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Message, MessageSegment
from nonebot.params import CommandArg

# This file is intended to remain in this pack; load_plugin(Path(...)) can load it.
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from packlib import load_songs, lookup, DIFFICULTIES

matcher = on_command('舞萌查曲',priority=10,block=True)


@matcher.handle()
async def handle_song(args: Message = CommandArg()):
    query = args.extract_plain_text().strip()
    if not query or len(query)>200:
        await matcher.finish(MessageSegment.text('格式：舞萌查曲 <曲名/别名/落雪ID>'))
    # A small local file; offload disk IO to avoid blocking the event loop.
    import asyncio
    matches = await asyncio.to_thread(lambda:lookup(load_songs(),query,5))
    if not matches:
        await matcher.finish(MessageSegment.text('当前快照未找到该曲目。'))
    lines = []
    for song in matches:
        lines.append(f'{song["title"]} / {song["artist"]}（落雪ID {song["id"]}）')
        for chart in song['charts']:
            name = DIFFICULTIES[chart['difficulty']] if chart['type']!='utage' else 'UTAGE'
            if chart['type'] == 'utage':
                lines.append(f'宴会场：{chart["level"]}，不计普通Rating')
            else:
                lines.append(f'{chart["type"]} {name}：国服NET {chart.get("cn_level") or "未匹配"} / 落雪 {chart["level"]}；落雪社区定数 {chart["level_value"]}')
    # Remote metadata is always sent as a text segment, never parsed as CQ code.
    await matcher.finish(MessageSegment.text('\n'.join(lines)[:6000]))
