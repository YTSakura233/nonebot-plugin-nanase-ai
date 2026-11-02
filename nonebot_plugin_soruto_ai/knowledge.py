"""Offline administration: python -m nonebot_plugin_soruto_ai.knowledge import FILE."""
import argparse
import asyncio


async def run(args):
    import nonebot
    from .config import Config
    from .core import config, db, knowledge, schema
    nonebot.init()
    config.init(nonebot.get_plugin_config(Config))
    try:
        await schema.ensure_schema_async()
        count = await knowledge.import_document(args.file, args.collection, args.source)
        print(f'已导入 {count} 个片段。重启机器人后加载更新的知识库。')
    finally:
        await db.close_async_pool()


def main():
    parser = argparse.ArgumentParser(description='导入本地文档到ナナセ知识库')
    commands = parser.add_subparsers(dest='action', required=True)
    command = commands.add_parser('import')
    command.add_argument('file')
    command.add_argument('--collection', default='default')
    command.add_argument('--source')
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == '__main__':
    main()
