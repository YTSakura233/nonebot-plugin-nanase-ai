"""Local song/alias lookup and exact level filtering; no HTTP, DB or model."""
import argparse
import json
import sys
from packlib import load_songs, lookup, ROOT


def main():
    if hasattr(sys.stdout,'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description='舞萌知识库离线查询')
    parser.add_argument('query',nargs='?',help='曲名、社区别名或落雪ID')
    parser.add_argument('--level',help='精确显示等级，例如 12 或 12+，默认国服NET快照')
    parser.add_argument('--level-source',choices=('cn','lxns'),default='cn',help='等级来源，默认国服NET社区快照')
    parser.add_argument('--limit',type=int,default=10)
    args = parser.parse_args()
    if bool(args.query) == bool(args.level):
        parser.error('exactly one of query or --level is required')
    if args.level:
        filename = 'cn_level_index.json' if args.level_source == 'cn' else 'level_index.json'
        index = json.loads((ROOT/'data'/filename).read_text(encoding='utf-8'))
        result = index.get(args.level,[])[:max(1,min(args.limit,100))]
    else:
        result = lookup(load_songs(),args.query,args.limit)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
