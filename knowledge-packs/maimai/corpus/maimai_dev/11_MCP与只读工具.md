# 只读MCP：让模型精确查曲

本包examples/mcp_server.py是可选本地stdio服务，只提供search_song(query)。它读取本包JSON、返回最多五首候选，没有HTTP、账号写入或Shell执行工具。安装依赖为mcp>=2.3,<3，示例使用该主版本的MCPServer接口；不同SDK版本不要照抄接口名。[MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)

## 已有Ubuntu / Conda环境的依赖

2026-11-02补充：已报告的Python3.11 / FastAPI0.115.12环境中，直接安装最新MCP间接依赖可能带入不兼容的Starlette。该环境已验证MCP2.3.0、SSE-Starlette3.0.2、Starlette0.46.2、FastAPI0.115.12组合。若同时使用quote0.4.2，HTTPX应为0.27.2，并先更新ナナセ至0.1.2（0.1.1要求HTTPX>=0.28）。兼容约束位于插件源码的constraints/ubuntu-py311-fastapi0115.txt。

先激活运行机器人的Conda环境并保存pip freeze，再按环境约束统一安装；完成后执行python -m pip check。该组合仅针对上述已报告环境，不要求其他环境降级FastAPI。独立MCP子进程的Python路径应使用同一环境中sys.executable的绝对路径。

## ナナセ配置示例

以下把包放在机器人工作目录下的maimai-knowledge；Python路径和脚本路径按服务器实际值填写：

```json
{
  "maimai": {
    "transport": "stdio",
    "command": "python",
    "args": ["./maimai-knowledge/examples/mcp_server.py"],
    "allowed_tools": ["search_song"],
    "readonly_tools": ["search_song"]
  }
}
```

上述对象放进SORUTO_MCP_SERVERS，另需SORUTO_ENABLE_TOOLS=true。allowed_tools使用源服务器工具名；运行时暴露给模型的名字可能带服务器命名空间，以插件注册结果为准。闲聊工具集合还受独立配置限制，不因声明readonly就自动允许主动闲聊调用。

## 原创权限设计建议

每个工具只做一件事，查询输入限制长度，输出限制候选数，校验结果结构。调用者和目标用户不是一个概念；如果以后加个人查分工具，必须先落实授权与主体绑定，不能让模型传任意QQ就跳过校验。

stdio stdout属于协议通道，调试信息写stderr或日志；不要在服务启动时向stdout打印欢迎语。服务退出时关闭会话和子进程；工具超时不应该阻塞整个聊天。只读服务的错误可以说明未查到或资料异常，不能伪造一个看似成功的歌曲结果。
