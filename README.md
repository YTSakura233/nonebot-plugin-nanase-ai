# ナナセ AI

面向 **NoneBot2 / QQ OneBot V11** 的 AI 聊天插件，支持角色人格、好感度、长期记忆、群聊主动接话，以及 DeepSeek、网页搜索、MCP、Skills 和本地知识库。

由 [astrbot_plugin_soruto_ai](https://github.com/sbga-fake/maimaibots/tree/6bf9ad2335d81c416950798a89c52c3d32f81651/soruto/astrbot_plugin_soruto_ai) 移植而来，机器人名称为「ナナセ」。运行时不依赖 AstrBot，也不依赖其他舞萌插件。

**当前版本：0.1.3。** 仓库采用可直接克隆的本地插件结构，根目录就是插件代码；Python 模块名与配置前缀保留为 `nonebot_plugin_soruto_ai`、`SORUTO_`。

## 目录

- [功能](#功能)
- [运行要求](#运行要求)
- [安装与首次启动](#安装与首次启动)
- [聊天与命令](#聊天与命令)
- [模型与常用配置](#模型与常用配置)
- [搜索与 MCP](#搜索与-mcp)
- [Skills](#skills)
- [本地知识库](#本地知识库)
- [更新](#更新)
- [常见问题](#常见问题)
- [来源与验证范围](#来源与验证范围)

## 功能

- **角色聊天**：保留原版人格背景与好感度体系，emoji 与回复正文一起发送，不另发一条表情消息。
- **自然接话**：支持私聊、@、引用回复、近期接话及按内容判断的群聊插话。没有夜间静默时段，普通群消息也不会每条必回。
- **记忆与会话**：聊天原文、滚动摘要、长期事实分层管理，支持摘要、压缩、会话重置和个人记忆重置。
- **模型分工**：DeepSeek Flash 处理日常、策略、摘要和识图，Pro 处理复杂问答；回复可按需进行多轮工具调用。
- **外部资料**：内置网页搜索和读取，支持连接部署者配置的 MCP 服务、读取启用的 Skills、检索本地知识库。
- **群聊适配**：独立群白名单、封禁名单、三秒消息聚合、同聊天串行生成、闲聊去重和长回复拆分。

## 运行要求

| 项目 | 要求 |
| --- | --- |
| Python | 3.11 或以上 |
| NoneBot | NoneBot2 2.4 或以上，低于 3.0 |
| 适配器 | `nonebot-adapter-onebot` 2.4 或以上，使用 OneBot V11 |
| QQ 连接 | 已能正常收发消息的 OneBot V11 客户端及 NoneBot 连接配置 |
| 数据库 | MySQL 8 / MariaDB，使用 `utf8mb4`；不支持 SQLite |
| 模型服务 | DeepSeek 官方 API Key，以及可用的模型额度 |
| 其他 | Git；启用 MCP 时还需安装对应 MCP 服务及其运行环境 |

本插件不会代替机器人主程序配置驱动、OneBot 连接或 QQ 客户端。尚未搭建机器人时，先完成 [NoneBot 快速上手](https://nonebot.dev/docs/quick-start)，并确认 OneBot V11 能正常收发消息。

## 安装与首次启动

下文以机器人项目的 **`src/plugins`** 为插件目录。所有命令均从**机器人项目根目录**执行；若项目使用 `plugins`，将示例中的 `src/plugins` 统一替换为 `plugins`。

### 1. 克隆插件

```bash
git clone --branch main https://github.com/YTSakura233/nonebot-plugin-nanase-ai.git src/plugins/nonebot_plugin_soruto_ai
```

目录应类似：

```text
your-bot/
├── pyproject.toml
├── .env.prod                       # 或项目实际启用的环境配置文件
└── src/
    └── plugins/
        └── nonebot_plugin_soruto_ai/
            ├── __init__.py
            ├── config.py
            ├── core/
            ├── knowledge.py
            ├── models.py
            ├── ngwords.txt
            ├── system_prompt.md
            └── README.md
```

已有同名插件目录时，先备份并移走旧副本，再克隆。不要把整个仓库放进另一层 `nonebot_plugin_soruto_ai` 目录，也不要同时加载旧的已安装包与本地副本。

### 2. 安装依赖

进入**运行机器人的同一个 Python 环境**。使用 Conda 时，先激活机器人使用的环境，再执行：

```bash
python -m pip install \
  'nonebot2>=2.4,<3' \
  'nonebot-adapter-onebot>=2.4,<3' \
  'pydantic>=2.7,<3' \
  'aiomysql>=0.2,<1' \
  'httpx>=0.27.2,<1' \
  'PyYAML>=6,<7' \
  'jsonschema>=4.20,<5'

python -m pip check
```

本仓库只包含本地插件和说明，未提供 `pyproject.toml`、`setup.py` 或 PyPI 安装包，因此不使用 `pip install .`、`pip install -e .` 或 `nb plugin install nonebot-plugin-nanase-ai`。

只进行聊天时无需安装 MCP 或文档解析依赖。相关安装命令见后文对应章节。已有其他插件的环境，应先解决 `pip check` 报出的冲突，再启动机器人。

### 3. 配置 NoneBot 加载目录

在机器人项目的 `pyproject.toml` 中，将插件目录加入现有配置：

```toml
[tool.nonebot]
plugin_dirs = ["src/plugins"]
```

已有 `[tool.nonebot]` 时只合并 `plugin_dirs`，保留其他插件配置，不重复创建同名表。

自行编写启动入口、未通过上述配置加载目录的项目，可在 `nonebot.init()` 之后调用：

```python
nonebot.load_plugins("src/plugins")
```

目录加载与显式加载不要重复使用。使用 `plugin_dirs` 后，无需再把本插件写进第三方包的 `plugins` 列表。

### 4. 创建数据库

插件启动时会创建七张 `soruto_nb_` 前缀的表，**不会创建数据库本身**。先由数据库管理员创建数据库和账号。以下为数据库与机器人位于同一主机的示例，密码需自行替换：

```sql
CREATE DATABASE nanase
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

CREATE USER 'nanase'@'localhost'
  IDENTIFIED BY 'REPLACE_WITH_A_STRONG_PASSWORD';

GRANT SELECT, INSERT, UPDATE, DELETE, CREATE
  ON nanase.* TO 'nanase'@'localhost';
```

使用已有账号时，确认它具备目标数据库的建表和读写权限。数据库位于其他主机时，相应调整连接地址、账号的允许来源及网络配置。

### 5. 填写必要配置

将以下内容追加到**机器人当前启用的环境文件**，例如 `.env.prod` 或 `.env.dev`。文件位于机器人项目中，不放进插件 Git 仓库。替换 API Key、数据库密码与群号：

```dotenv
SORUTO_DEEPSEEK_API_KEY="your_deepseek_api_key"

SORUTO_DB_HOST="localhost"
SORUTO_DB_PORT=3306
SORUTO_DB_USER="nanase"
SORUTO_DB_PASSWORD="REPLACE_WITH_A_STRONG_PASSWORD"
SORUTO_DB_NAME="nanase"

SORUTO_ALLOWED_GROUPS=[123456789]
SORUTO_BANNED_USERS=[]

SORUTO_SIMPLE_MODELS=["deepseek-flash"]
SORUTO_COMPLEX_MODELS=["deepseek-v4-pro"]
SORUTO_VISION_MODELS=["deepseek-flash"]

# 先确认基本聊天正常；需要搜索、MCP 或 Skills 时再开启。
SORUTO_ENABLE_TOOLS=false
```

列表和字典配置使用 JSON 格式；QQ 号、群号使用数字。配置修改后需要重启机器人。

准入规则：

- 只有 `SORUTO_ALLOWED_GROUPS` 中的群可用；空列表不会开放任何群。
- 用户在获准群中发言后自动登记，随后才可私聊机器人。
- `SORUTO_BANNED_USERS` 和数据库中的封禁状态均会阻止使用。
- NoneBot `SUPERUSERS` 不绕过本插件的群白名单、登记与封禁检查。

### 6. 启动并测试

使用机器人项目原有的启动方式，例如：

```bash
nb run
```

成功初始化后，日志会出现：

```text
[soruto] NoneBot / OneBot V11 插件就绪。
```

在白名单群内发送 `/ai help` 查看帮助，再使用 QQ 的实际 @ 功能发送 `@机器人 你好，介绍一下自己`。确认群内使用正常后，可由已登记的用户进行私聊。

## 聊天与命令

### 如何触发

- **群聊**：@ 机器人或引用机器人的消息回复。普通发言由策略判断是否接话，单独喊名字也不保证触发。
- **私聊**：已登记且未封禁的用户直接发送消息。
- **图片**：随问题发送图片，交给视觉模型识别；每条最多处理 4 张、每张 8 MiB，支持 JPEG、PNG、GIF、WebP。

消息会进行约三秒聚合；长回复可能拆成多条。emoji 属于正文，不会为了表情另外发送一条消息。语音目前仅记录占位文字，不提供语音转写。

### 命令表

命令以 `/` 开头，直接发送即可，不要求同时 @ 机器人。

| 命令 | 用途 | 权限 / 范围 |
| --- | --- | --- |
| `/ai` | 查看个人状态、好感度与记忆 | 本人；私密事实仅私聊显示 |
| `/ai help` | 查看帮助 | 获准用户 |
| `/help` | 帮助别名，可关闭 | 获准用户 |
| `/summary` | 刷新并展示当前聊天摘要，保留原文 | 获准用户 |
| `/ai compact` | 压缩当前聊天，摘要保存成功后删除对应原文 | 群聊仅群主；私聊本人 |
| `/ai reset` | 重置当前聊天的原文与摘要，保留长期事实和好感度 | 群聊仅群主；私聊本人；需确认 |
| `/ai forget` | 清除本人长期记忆并将好感度重置为初始值 20 | 本人；需确认；24 小时冷却 |
| `/ai on` | 开启本人的定向回复 | 本人 |
| `/ai off` | 关闭本人的定向回复 | 本人；突破状态下需额外确认 |
| `/ai breakthrough` | 好感度达到 100 时申请突破至 101 | 本人；需确认 |

需要确认的操作，先发送原命令，再由本人在**同一聊天、两分钟内**添加 `confirm`，例如：

```text
/ai reset
/ai reset confirm
```

群管理员和 `SUPERUSERS` 不能代替群主执行群聊的 compact/reset。

`/ai off` 在私聊中静音，在群聊中关闭对该用户的定向回复；机器人仍可能参与群内普通闲聊。突破后关闭回复会清除本人的长期事实、将好感度降到 -100，并有三天不能重置的限制；以命令中的确认提示为准。

### 记忆范围

会话原文与摘要按机器人 QQ、聊天类型和聊天目标隔离，个人好感度及长期事实按用户 QQ 共享。公开群聊不载入跨聊天原文或私密事实；私聊可关联该用户自己的其他聊天。

`reset` 不清除个人长期事实，`forget` 不删除聊天原文，两者用途不同。模型与工具请求会将本轮所需的聊天上下文、图片或检索片段发送给所配置的外部服务；部署者应向群成员说明机器人会保存和处理聊天记录。

## 模型与常用配置

当前实现使用固定的 **DeepSeek 官方 API** 地址，不提供第三方中转地址配置。默认模型及其视觉能力可参考 [DeepSeek 官方模型说明](https://api-docs.deepseek.com/quick_start/pricing/)。

| 配置项 | 默认值 | 用途 |
| --- | --- | --- |
| `SORUTO_SIMPLE_MODELS` | `["deepseek-flash"]` | 日常回答、策略、摘要等 |
| `SORUTO_COMPLEX_MODELS` | `["deepseek-v4-pro"]` | 复杂问答与推理 |
| `SORUTO_VISION_MODELS` | `["deepseek-flash"]` | 图片识别及带原图的回答 |
| `SORUTO_FALLBACK_MODELS` | `[]` | 可选的备用模型列表 |
| `SORUTO_ENABLE_TOOLS` | `false` | 开放搜索、MCP 和 Skills 工具 |
| `SORUTO_MODEL_CONCURRENCY` | `8` | 模型请求并发上限 |
| `SORUTO_LLM_DEADLINE_SECONDS` | `90` | 一轮定向回答的模型时间预算（秒） |
| `SORUTO_MAX_TOKENS` | `4096` | 模型输出 token 上限 |
| `SORUTO_MAX_AGENT_STEPS` | `10` | 定向工具循环步数上限 |
| `SORUTO_MAX_TOOL_CALLS` | `12` | 每轮工具调用上限 |
| `SORUTO_TOOL_TIMEOUT_SECONDS` | `15` | 单次工具调用超时（秒） |
| `SORUTO_CASUAL_MAX_AGENT_STEPS` | `3` | 普通闲聊的工具循环步数上限 |
| `SORUTO_CASUAL_DEADLINE_SECONDS` | `20` | 普通闲聊的时间预算（秒） |
| `SORUTO_MAX_PENDING_TURNS` | `64` | 排队及运行中的回合上限 |
| `SORUTO_REPLY_UNITS` | `1800` | 长回复拆分的长度预算 |
| `SORUTO_ENABLE_HELP_ALIAS` | `true` | 是否接管独立的 `/help` |
| `SORUTO_IGNORE_PREFIXES` | `["/", "mai.", "SGWCMAID"]` | 非本插件命令的消息忽略前缀 |

带原图的请求使用视觉链，不将原图交给不支持视觉的 Pro。模型数组按顺序尝试；备用切换受失败类型和工具执行状态限制，不表示每次失败都会重放请求。对话与辅助策略、摘要、识图、查询扩展均可能产生模型费用。

全部配置字段及取值范围见 [config.py](config.py)。

## 搜索与 MCP

### 网页搜索

开启工具即可提供内置的 `web_search` 和 `web_fetch`，不要求安装 MCP SDK：

```dotenv
SORUTO_ENABLE_TOOLS=true
```

搜索与读取使用同一 DeepSeek API Key，调用官方 [Search / Fetch API](https://api-docs.deepseek.com/guides/search/)，按官方规则计费。模型根据本轮需要选择工具，开启工具不代表每次回答都会搜索。

### 安装 MCP 客户端依赖

需要连接 MCP 服务时，在机器人使用的 Python 环境安装当前验证过的 SDK 组合：

```bash
python -m pip install 'mcp==2.3.0' 'sse-starlette==3.0.2'
python -m pip check
```

本插件使用 **MCP Python SDK 2.x**，支持 stdio、Streamable HTTP 和 SSE。参考 [MCP Python SDK 文档](https://py.sdk.modelcontextprotocol.io/)。安装 SDK 只是安装客户端依赖；实际的 MCP 服务器需按照其作者文档单独安装、配置。

### 连接 Streamable HTTP 服务

下面的地址与 `read_note` 均为示例，替换成实际服务器的地址和工具名：

```dotenv
SORUTO_ENABLE_TOOLS=true
SORUTO_MCP_SERVERS='{"notes":{"transport":"streamable_http","url":"https://example.com/mcp","headers":{},"allowed_tools":["read_note"],"readonly_tools":["read_note"]}}'
```

SSE 服务使用 `"transport":"sse"`，并填写服务实际提供的 SSE URL。

### 连接本地 stdio 服务

以下示例要求指定路径已经存在可运行的 MCP 服务脚本；`command` 应指向其所需环境的可执行文件：

```dotenv
SORUTO_ENABLE_TOOLS=true
SORUTO_MCP_SERVERS='{"notes":{"transport":"stdio","command":"/opt/your-bot/.venv/bin/python","args":["/opt/your-bot/mcp/server.py"],"cwd":"/opt/your-bot/mcp","allowed_tools":["read_note"],"readonly_tools":["read_note"]}}'
```

使用 Conda 时，将 `command` 替换为实际环境中的 Python 绝对路径。需要额外环境变量时，可使用该服务的 `env` 字段。

### 工具权限

- `allowed_tools`：允许模型使用的服务端工具名；空列表表示不开放任何工具。
- `readonly_tools`：上述列表中经部署者确认只读的工具，必须是 `allowed_tools` 的子集。标记本身不会阻止服务端执行写入，应核对工具实际行为。
- `allowed_users`、`allowed_groups`：可进一步限制服务的使用者和群；默认空列表表示不增加这一项限制。设置群限制后，该服务不向私聊开放。
- 普通群聊插话只允许只读工具，且还需出现在 `SORUTO_CASUAL_TOOL_NAMES` 中。MCP 工具在这里使用 `服务名/工具名`：

```dotenv
SORUTO_CASUAL_TOOL_NAMES=["web_search","web_fetch","notes/read_note"]
```

MCP 工具参数按服务返回的 JSON Schema 校验。机器人只启动部署者固定配置的 stdio 进程，不会根据聊天消息安装服务器。会话重置不能撤销已经完成的外部工具操作。

### 已有旧版 FastAPI 的环境

如果环境中仍在使用 **FastAPI 0.115.12**，不要单独将 Starlette 或 SSE 升级到最新版本。该环境在 Python 3.11 下验证过的核心兼容组合为：

```bash
python -m pip freeze > before-mcp-install.txt
python -m pip install \
  'mcp==2.3.0' 'sse-starlette==3.0.2' \
  'fastapi==0.115.12' 'starlette==0.46.2' 'httpx==0.27.2'
python -m pip check
```

此组合只用于相应旧环境，不是所有 NoneBot 项目的通用锁定版本。其他插件对 `aiofiles`、Pillow 等的要求仍需分别满足；不要使用 `--no-deps` 隐藏冲突。

## Skills

Skills 是提供给模型按需阅读的说明和引用资料，不是另一个插件安装系统。将技能放在机器人主机的独立目录中，例如：

```text
skills/
└── game-helper/
    ├── SKILL.md
    └── reference.md
```

`SKILL.md` 示例：

```markdown
---
name: game-helper
description: 回答游戏问题时核对资料来源和版本。
---

回答前确认用户所问的游戏版本；必要时使用已开放的搜索工具。
详细术语见 reference.md，资料不足时说明不确定之处。
```

启用配置：

```dotenv
SORUTO_ENABLE_TOOLS=true
SORUTO_SKILLS_DIR="./skills"
SORUTO_ENABLED_SKILLS=["game-helper"]
```

相对路径以机器人工作目录为基准；也可填写绝对路径。目录名、frontmatter 的 `name` 和启用列表需一致，名称使用小写字母、数字及中间连字符。

只加载显式启用的技能，单文件最多 64 KiB，不能读取技能目录之外的引用。Skills 仅能指导当前已开放的搜索/MCP 工具，不执行本地 Python/Shell 脚本，也不会通过技能正文增加工具权限；普通闲聊默认不开放技能读取。

## 本地知识库

将资料放在机器人主机的独立目录中，再配置集合。**本仓库不附带预制舞萌知识库或其他资料包**，可导入自己有权使用的资料。

```text
knowledge/
├── intro.md              # 属于 default 集合
└── maimai/
    ├── rules.md          # 属于 maimai 集合
    └── songs.md
```

```dotenv
SORUTO_KNOWLEDGE_DIR="./knowledge"
SORUTO_KNOWLEDGE_COLLECTIONS=["default","maimai"]
SORUTO_KNOWLEDGE_TOP_K=4
SORUTO_KNOWLEDGE_QUERY_EXPANSION=true
```

知识库配置与 MCP 独立。顶层文件属于 `default`，子目录中的文件以第一层目录名作为集合名。默认集合列表为空，不导入或检索任何集合。

支持 Markdown、TXT；需要导入文字 PDF 或 Word `.docx` 时，额外安装：

```bash
python -m pip install 'pypdf>=5' 'python-docx>=1.1'
python -m pip check
```

启动时会导入所选集合并加载数据库索引，不需要另外执行导入脚本。检索使用中英文 BM25、可选的 DeepSeek 同义查询扩展和本轮策略选择，附带集合/文件/片段来源；不要求向量数据库。查询扩展会额外调用模型，可关闭相应配置以减少请求。

限制与维护行为：

- 单文件最多 4 MiB，PDF 最多 500 页，配置目录最多 200 份支持格式的文档，启用集合最多 20,000 个片段。
- 同一集合、同一来源重新导入时事务替换；解析失败不先删除旧内容。
- 磁盘文件删除后，已入库片段不会自动删除。彻底移除资料需由数据库管理者按集合和来源删除知识表记录，再重启加载。
- 扫描 PDF 不自动 OCR，语音文件不能作为文字资料导入。
- 启用的集合供所有获准聊天使用，资料应适合该范围的用户访问。

## 更新

停止机器人后，在项目根目录拉取 `main`：

```bash
git -C src/plugins/nonebot_plugin_soruto_ai pull --ff-only origin main
python -m pip check
```

检查成功后，按原有方式重新启动机器人。修改 `.env`、人格提示词或其他本地配置后，也需要重启才能应用；如直接修改了仓库跟踪文件，先妥善保留改动再处理更新冲突。

现有自动更新脚本只需增加上述 `git -C ... pull`，并在更新完成后统一重启。未来版本若新增依赖，应按该版本说明在同一 Python 环境安装。插件本身不提供聊天更新命令，不自动运行 Git 或 Shell。

## 常见问题

### 克隆了，但 NoneBot 没有加载

确认目标目录直接包含 `__init__.py`，目录名为 `nonebot_plugin_soruto_ai`；检查 `plugin_dirs` 是否与实际的 `src/plugins` 或 `plugins` 一致。不要使用默认仓库名作为另一层外壳目录。

出现 `ModuleNotFoundError` 时，先检查缺少的依赖是否装在运行机器人的 Python 环境中：

```bash
python -V
python -m pip --version
python -m pip check
```

### 日志显示初始化失败，机器人不回复

启动失败时插件会停止接收聊天。检查当前启用的环境文件、数据库账号、数据库名称，以及可选的知识库/技能路径。设置了目录但目录不存在，也可能导致初始化失败；未使用这些能力时不要填写路径。

常见 MySQL 错误码：`1049` 表示数据库不存在，`1045` 表示认证或权限问题，`2003` 通常需要检查服务、端口与网络连接。插件只自动建表，不自动建库。若认证提示需要 `cryptography`，在机器人环境安装该包后重试。

### 群里可以用，私聊不回复

先由该用户在白名单群中发言完成登记，再检查封禁状态和 `/ai on`。新用户直接私聊不会自动获得使用权限。

### 普通群消息有时不回复

这是选择性接话的预期行为。测试时使用实际 @ 或引用回复，并确认白名单、个人开关及初始化状态。只发送「ナナセ」不等同于明确 @。

### 文字收到了，仍然出现 HTTPStatusError

一次回答可能包含策略、正式回答、摘要或工具等多个请求，正文发送成功不代表其他请求均成功。0.1.3 的日志会保留 HTTP 状态码、已知请求类别、模型用途和插件源码位置，结合这些字段定位失败环节。

例如 `api=DeepSeek/search` 指向搜索请求，`context=model_summary` 指向摘要模型调用。检查对应服务的 Key、额度、模型名和网络；不要只根据错误类名推断原因。官方状态码含义见 [DeepSeek 错误码](https://api-docs.deepseek.com/quick_start/error_codes/) 与 [搜索/读取错误说明](https://api-docs.deepseek.com/guides/search/#errors)。

### 与其他插件的 /help 冲突

```dotenv
SORUTO_ENABLE_HELP_ALIAS=false
```

重启后使用 `/ai help`，不再接管独立的 `/help`。

### MCP 配置了却没有工具

依次检查 SDK 2.x、`SORUTO_ENABLE_TOOLS`、连接方式、服务端实际工具名与 `allowed_tools`。本地 stdio 使用对应环境的可执行文件绝对路径。普通闲聊还需要只读标记及 `SORUTO_CASUAL_TOOL_NAMES`；模型也可能判断本轮不需要调用工具。

提交问题时，请提供插件版本、Python/NoneBot 版本、部署方式及脱敏后的相关日志，不要公开 API Key、数据库密码或聊天原文。

## 来源与验证范围

人格提示词、禁词及部分会话/好感度设计源自 [maimaibots 的 AstrBot 插件](https://github.com/sbga-fake/maimaibots/tree/6bf9ad2335d81c416950798a89c52c3d32f81651/soruto/astrbot_plugin_soruto_ai)，基准提交为 `6bf9ad2335d81c416950798a89c52c3d32f81651`。感谢原作者的工作。原目录未附单独许可证，本仓库不另行声明上游内容的授权条款。

本版本重新实现了 NoneBot/QQ 接入、数据库初始化、DeepSeek 调用、MCP、Skills 和知识库适配。开发阶段通过 127 项离线回归，并验证过真实 MCP SDK 本地 stdio、直接克隆到插件目录后的 NoneBot 加载和资源读取；不代表已对所有 QQ 客户端、生产数据库或付费 API 完成实机验收。

本仓库保留部署所需插件文件与 README，未包含开发测试工程、打包工程、API 凭据或预制知识资料。
