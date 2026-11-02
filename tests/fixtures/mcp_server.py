"""Local-only MCP integration fixture; no model, network or database."""
import site
import sys

if len(sys.argv) > 1:
    site.addsitedir(sys.argv[1])

from mcp.server import MCPServer

server = MCPServer('offline-test')


@server.tool()
def read_note(topic: str) -> str:
    return 'verified:' + topic


@server.tool()
def write_note(topic: str) -> str:
    return 'write:' + topic


if __name__ == '__main__':
    server.run()
