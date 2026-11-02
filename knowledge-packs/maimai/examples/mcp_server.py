"""Optional read-only server; pip install 'mcp>=2.3,<3'. Uses local JSON only."""
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from packlib import load_songs, lookup


def search_song(query: str) -> list[dict]:
    """查曲名、别名或落雪ID；社区资料快照，最多返回5首完整资料。"""
    return lookup(load_songs(),query,5)


def main():
    from mcp.server import MCPServer
    server = MCPServer('maimai-knowledge')
    server.tool()(search_song)
    server.run()


if __name__ == '__main__':
    main()
