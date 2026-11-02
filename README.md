# NoneBot ナナセ AI 插件

基于 [原版 astrbot_plugin_soruto_ai](https://github.com/sbga-fake/maimaibots/tree/6bf9ad2335d81c416950798a89c52c3d32f81651/soruto/astrbot_plugin_soruto_ai) 的独立 NoneBot2 / QQ OneBot V11 移植。模块名为 `nonebot_plugin_soruto_ai`；本目录可独立复制、安装，运行时不依赖父目录的舞萌账号插件。

保留人格、好感度、主动闲聊、三层记忆、会话摘要/压缩/重置、三秒聚合与回复去重。重建 DeepSeek 官方 API、多步工具循环、网页搜索/读取、MCP、只读 Skills 和本地知识库。emoji直接并入回复正文，不单独发送表情消息。

独立仓库：[YTSakura233/nonebot-plugin-nanase-ai](https://github.com/YTSakura233/nonebot-plugin-nanase-ai)，更新分支为main。导入名继续使用nonebot_plugin_soruto_ai，保留现有配置键和数据表。

## 安装

需要 Python 3.11+、NoneBot2 2.4+、OneBot V11 适配器，以及使用 utf8mb4 的 MySQL 8 / MariaDB。QQ连接由你的OneBot客户端提供。

进入本仓库根目录，在运行机器人的同一Python/Conda环境中安装（未发布到PyPI）：

```bash
python -m pip install '.[mcp,documents]'
```

其他机器先复制目录，再把路径替换为复制后的绝对路径。`mcp` 提供 SDK；`documents` 提供PDF/Word导入；不使用这些能力时可去掉 extras。

### Ubuntu / Conda 中已有其他插件

在运行 NoneBot 的同一 Conda 环境中安装。先保存 `python -m pip freeze`，查看 `python -m pip check`，不要把 MCP 的最新间接依赖直接升级到已有机器人环境。

对于已报告的 Python 3.11、FastAPI 0.115.12、quote 0.4.2、marshoai、argot、setu-now 共存环境，0.1.2 起兼容 HTTPX 0.27.2，并将 MCP extra 的 SSE 约束为3.0系列。该环境使用的验证组合见 [兼容约束](constraints/ubuntu-py311-fastapi0115.txt)。在复制后的本插件源码目录执行：

```bash
python -m pip freeze > before-mcp-fix.txt
python -m pip install -c constraints/ubuntu-py311-fastapi0115.txt '.[mcp]' 'fastapi==0.115.12' 'aiofiles==24.1.0' 'Pillow==11.1.0'
python -m pip check
```

该约束只针对上述环境，不是完整环境锁。MCP 2.3使用独立的httpx2；ナナセ与quote可使用httpx 0.27.2。SSE 3.6要求Starlette>=0.49.1，与FastAPI 0.115.12的Starlette<0.47要求不相容，须同时调整SSE和Starlette。0.1.1声明的HTTPX>=0.28也与quote 0.4.2不相容，修复时更新插件，不能使用`--no-deps`掩盖冲突。

本地已用兼容组合通过116项回归及真实SDK stdio测试；这不替代部署环境中其余插件的`pip check`和启动验证。

在机器人现有的配置中追加插件，保留其他插件：

```toml
[tool.nonebot]
plugins = ["nonebot_plugin_soruto_ai"]
```

或在 `nonebot.init()` 后调用 `nonebot.load_plugin("nonebot_plugin_soruto_ai")`。驱动和OneBot适配器仍由机器人主程序加载。

参照 [.env.example](.env.example) 在机器人运行目录配置环境。至少填写 `SORUTO_DEEPSEEK_API_KEY`、数据库连接项和 `SORUTO_ALLOWED_GROUPS`。数据库本身需预先创建；启动时自动创建七张 `soruto_nb_` 表，需要建表及读写权限。初始化失败则不接收聊天。

凭据只填在部署环境，不提交仓库。本项目不自动部署、重启机器人或操作生产库。

## 命令

| 命令 | 行为 |
| --- | --- |
| `/ai` | 本人状态、好感度及记忆；私密事实仅私聊显示 |
| `/ai help`、`/help` | 帮助；可关闭全局help别名以便与其他插件共存 |
| `/summary` | 合并新消息并展示摘要，不删原文；普通成员可用 |
| `/ai compact` | 压缩当前聊天，摘要保存成功后才删对应原文 |
| `/ai reset` | 清当前聊天原文和摘要，保留长期事实及好感度 |
| `/ai forget` | 重置本人长期事实和好感度，24小时冷却 |
| `/ai on`、`/ai off` | 开关本人定向回复 |
| `/ai breakthrough` | 好感度100时申请突破，确认后为101 |

reset、forget、breakthrough 先申请，再由本人在同一聊天2分钟内添加 `confirm` 确认，例如 `/ai reset confirm`。群聊compact/reset仅群主可用，管理员及SUPERUSER不代替群主；确认时再次查身份。私聊由本人操作，匿名消息不接收。

突破后off也需确认：个人事实清空、好感度降至-100、关闭定向回复，3天内不能重置。初始/forget后的好感度沿用上游实际代码的20；模型不能绕过确认从100进入101。forget不清聊天原文，reset不清长期事实。

准入沿用原规则：只接收 `SORUTO_ALLOWED_GROUPS` 中的群；获准群的发言成员自动登记；私聊仅已登记未封禁者可用。配置 `SORUTO_BANNED_USERS`，或由数据库管理者设置 `soruto_nb_users.is_banned=1` 封禁用户。不新增SUPERUSER准入豁免。配置修改后重启生效；空群白名单不开放任何群。

## 聊天行为

- 私聊、@、引用机器人、近期定向接话和突破用户沿用原策略；普通群消息按内容决定是否自然插话，不使用随机概率。全天均可参与普通群聊，取消22:00—06:00的主动闲聊限制。
- off在私聊静音，在群里关闭对该用户定向回复，全天仍可对群闲聊。关闭回复不等于删除聊天记录。
- 三秒聚合；不同用户显式问题分别保留。同聊天串行生成，闲聊旧结果随新消息失效，定向问答不走闲聊重复过滤。最多64个排队/运行回合，超限的定向请求给忙碌提示。
- 聊天键包括机器人QQ、聊天类型和目标号；个人好感度/事实按用户QQ共享。原文有界注入、摘要滚动压缩、事实按相关性检索并由策略挑选。公开群不载入跨聊天原文或私密事实；私聊可衔接该用户自己的其他聊天。
- 图片先转写，再按需给Flash原图；每条最多4张、每张8 MiB，接受JPEG/PNG/GIF/WebP。语音仅占位，不提供语音识别；扫描PDF不自动OCR。
- 长回复分段，定向首段引用，主动闲聊不引用、不@发言人。OneBot没有输入中状态，不伪造该协议能力。
- emoji作为正文的一部分发送；同一个emoji不重复附加，不另发一条emoji消息。没有正文时，不发送旧协议的sticker字段，也不记录为成功回复。
- 直接抓取网页和图片时校验并固定公网IP，保留原Host/TLS校验，重定向逐跳验证；这两种下载不使用环境代理。DeepSeek API和MCP仍使用各自的网络配置。
- reset/compact取消旧生成；已执行的外部MCP操作无法由会话重置撤销。

## DeepSeek

默认Flash负责日常、策略、摘要和视觉，Pro负责复杂问答。带原图的请求始终使用视觉链，不送入不支持图片的Pro。辅助策略用JSON，正式回答为普通正文。复杂工具循环按官方要求回传本轮 `reasoning_content`，不向用户展示或作为长期记忆保存。

`SORUTO_ENABLE_TOOLS` 默认false，示例环境显式设true。定向最多10步/90秒；闲聊默认3步/20秒且只读白名单；每轮最多12次工具调用，单工具默认15秒。仅429、超时、连接失败或5xx在执行工具前可切换配置的备用模型；拒答、空结果及配置错误不切换，工具执行后不重放。

内置 `web_search`、`web_fetch` 调用 [DeepSeek Search/Fetch](https://api-docs.deepseek.com/guides/search/)，保留实际来源URL。模型与搜索按官方计费。

## MCP

安装 `[mcp]` 后使用SDK 2.x，支持stdio、Streamable HTTP及SSE。只连接部署者配置的服务，不自动安装服务器。stdio只启动配置中的固定MCP服务进程。

以下URL、工具名为占位，须换成服务器实际提供的值：

```dotenv
SORUTO_MCP_SERVERS='{"repo":{"transport":"streamable_http","url":"https://example.com/mcp","headers":{},"allowed_tools":["read_file","search_repository"],"readonly_tools":["read_file","search_repository"],"allowed_groups":[123456789]}}'
SORUTO_CASUAL_TOOL_NAMES=["web_search","web_fetch","repo/read_file","repo/search_repository"]
```

stdio使用 `transport=stdio`，填写 `command`、`args`，可选 `env`、`cwd`。SSE使用 `transport=sse` 与对应URL。

`allowed_tools` 为空则不开放该服务工具。`readonly_tools` 必须是其子集；闲聊还与 `SORUTO_CASUAL_TOOL_NAMES` 取交集，MCP名写为 `服务/工具`。可通过 `allowed_users`、`allowed_groups` 继续限权，空集合不增加该项限制。参数按JSON Schema验证；连接失败不宣称查证成功。

## Skills

配置 `SORUTO_SKILLS_DIR`、`SORUTO_ENABLED_SKILLS`。只加载点名目录的 `SKILL.md`，要求YAML frontmatter中的name与目录一致，并包含description。模型按需读取正文与目录内引用；禁止越目录与符号链接逃逸，单文件64 KiB。

Skills只指导当前开放的搜索/MCP工具，不执行本地Python/Shell脚本，不因正文或allowed-tools字段扩大权限。闲聊默认不开放技能读取。

## 知识库

配置 `SORUTO_KNOWLEDGE_DIR`、`SORUTO_KNOWLEDGE_COLLECTIONS`。顶层文件属于default集合，一层子目录名作为集合名。支持Markdown/TXT，安装 `[documents]` 后支持文字PDF/Word及Word表格。

启动时导入所选集合；单文件4 MiB、单PDF500页、目录200份文档、索引20000片段。同一来源事务替换，解析失败不先删旧内容。移除磁盘文件不会自动删除数据库资料。

也可在机器人运行目录手动导入，再重启加载：

```bash
python -m nonebot_plugin_soruto_ai.knowledge import ./guide.md --collection default
```

移除来源由数据库管理者按collection_name、source删除相应知识表记录后重启。检索采用中英文BM25召回、可选DeepSeek同义查询扩展、本轮策略挑选，携带“集合/文件#片段”来源。没有宣称实现AstrBot的向量检索。选定集合供所有获准聊天使用，不应把未授权公开的文件放入该集合。

## 验证

```bash
python -m pip install -e '.[dev,mcp,documents]'
python -m pytest -q
python -m compileall -q nonebot_plugin_soruto_ai
python -m build --no-isolation
```

离线测试拦截真实HTTP/数据库，模型与QQ使用模拟对象；另有真实MCP SDK本地stdio和NoneBot加载检查。实际QQ客户端、数据库及付费API仍需部署后联调。

来源及差异见 [UPSTREAM.md](UPSTREAM.md)，设计见 [docs/方案设计.md](docs/方案设计.md)。

## GitHub更新与诊断

独立仓库可克隆到服务器固定目录，在同一Conda环境中安装。不要让同一个模块同时从plugins副本和已安装包加载。

```bash
git clone https://github.com/YTSakura233/nonebot-plugin-nanase-ai.git
cd nonebot-plugin-nanase-ai
python -m pip install -e '.[mcp]'
```

已存在FastAPI0.115.12/quote0.4.2的Python3.11环境，安装与更新时继续使用constraints/ubuntu-py311-fastapi0115.txt，按上面的Conda兼容说明处理。

自动更新程序应拉取本仓库main分支，安装成功并通过pip check后重启NoneBot。本插件不新增聊天更新命令，也不自动执行Git/Shell；更新任务和重启由部署者现有机制管理。数据库和机器人.env放在部署环境，不提交到仓库。

0.1.3起，错误日志保留HTTP状态码、已知请求类别、模型调用用途和插件源码位置；数据库异常保留MySQL数字错误码。日志不输出异常原文、完整URL、请求/响应正文、密钥或聊天内容。HTTPStatusError仍表示某次请求失败，不能仅凭其他回复成功就认定该错误已解决。

仓库knowledge-packs/maimai为配套舞萌知识库（GitHub源码中提供，wheel不内嵌）。需要时将SORUTO_KNOWLEDGE_DIR指向该目录的corpus，并启用相应集合；快照来源和更新说明见其README。
