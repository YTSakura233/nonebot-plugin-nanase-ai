# 舞萌知识库 · ナナセ用

版本 **1.0.2**，曲库资料核查日期 **2026-11-01**，插件与MCP安装说明于 **2026-11-02**更新。以国服舞萌DX为主，补充日服/国际服区别、公开接口、谱面格式和原创示例代码。可直接用于现有ナナセ NoneBot插件的本地知识检索，也可作为独立Markdown资料阅读。

[完整文档目录](INDEX.md) · [来源与差异](SOURCES.md) · [验证记录](docs/验证记录.md)

## 包含什么

| 内容 | 本版规模 |
| --- | --- |
| 可导入Markdown | 130份，约3316个现有插件片段 |
| 人工编写规则/开发文档 | 40份：玩法26、开发12、本地插件2 |
| 落雪歌曲条目 | 1360条，含特殊、未配信或禁用资料，不等于1360首均可立即游玩 |
| 谱面记录 | 5623张：标准2260、DX3298、宴会场65 |
| 国服NET社区快照 | 1294首、5520张常规谱面 |
| 已关联社区别名 | 2933个，允许同一别名多义 |
| 等级索引 | 国服NET与落雪分别生成，12与12+严格区分 |
| 原创代码 | Rating/B50/失分、查曲CLI、快照更新、简化simai时序、NoneBot和只读MCP示例 |

玩法覆盖机台流程、全部基础音符、滑条读谱、触区、难度/定数/拟合、判定、FC/AP、达成率、DX分、Rating、新旧池、练习与设置、歌曲/地区版本、旅行解锁、宴会场、段位对战、牌子、万花筒概览、账号与术语、赛事规则。

开发覆盖数据模型、源站ID差异、物量结构、Decimal计算、公开API与OAuth、MySQL/MariaDB表、更新校验、simai解析架构、NoneBot、BM25、MCP和部署排错。官方客户端源码、音乐、曲绘与完整商业谱面资源不在本包。

## 给ナナセ接入

将整个目录放到**机器人进程工作目录**下并命名为maimai-knowledge。将以下内容合入机器人已有.env；数据库与模型配置继续使用原配置：

```dotenv
SORUTO_KNOWLEDGE_DIR="./maimai-knowledge/corpus"
SORUTO_KNOWLEDGE_COLLECTIONS=["maimai_game","maimai_songs","maimai_levels","maimai_dev","maimai_project"]
SORUTO_KNOWLEDGE_QUERY_EXPANSION=true
```

重启机器人后，现有导入器会将启用集合导入MySQL/MariaDB。自然提问例如“AP+为什么DX分没满”“真爱歌的紫谱资料”“如何计算13.7的鸟加底分”即可触发相关检索。

只读游戏知识可仅启用maimai_game、maimai_songs、maimai_levels；maimai_dev用于开发问答，maimai_project描述ナナセ 0.1.3实现。按需启用不会修改个人权限或模型配置。

本包已低于当前插件200文档、20000片段、单文档4MiB上限。实际导入仍需要你部署环境已有的数据库；本次未连接用户数据库或QQ进行上线操作。

## 离线查曲与计算

在本包根目录，Python >=3.11：

```bash
python scripts/lookup.py "真爱歌"
python scripts/lookup.py "Oshama Scramble!"
python scripts/lookup.py 8
python scripts/lookup.py --level 12+ --limit 20
python scripts/lookup.py --level 12+ --level-source lxns --limit 20
python examples/simai_timing.py
python scripts/validate_pack.py
```

前三种查询返回候选及完整谱面资料；精确等级默认使用国服NET社区快照，指定--level-source lxns才按落雪等级过滤。查询不会联网、登录或修改成绩。

```python
from examples.maimai_math import rating
assert rating('13.7','100.5') == (308,'SSS+')
```

Rating示例采用固定版本水鱼社区算法，包括特殊边界；它不宣称所有查分器与官方内部实现必然相同。

## 目录

```text
corpus/maimai_game/      游戏与练习文档
corpus/maimai_songs/     自动逐曲档案
corpus/maimai_levels/    两源精确等级索引
corpus/maimai_dev/       开发文档
corpus/maimai_project/   ナナセ本地实现说明
data/                   原始快照、归一化歌曲与索引
examples/               原创Python与SQL例子
scripts/                构建、验证、更新与查询
docs/                   验证记录、集成检查结果
SOURCES.md              来源、证据级别与更新限制
manifest.json           快照日期、统计与资料SHA-256
```

## 更新公开资料

```bash
python scripts/refresh.py --game-version 25500 --dry-run
```

确认来源、统计及差异后，保存旧ZIP备份、停止机器人，再去掉--dry-run执行。更新器在临时目录验证候选，发布为多文件复制；发布中断可从旧ZIP恢复。换游戏大版本时先核对落雪版本参数，不能永久沿用25500。

完全离线重建：

```bash
python scripts/build_pack.py
python scripts/validate_pack.py
python scripts/package.py
```

删除/改名磁盘来源不会自动清除现有插件数据库里的旧来源。若生成分片减少或调整集合，管理员按明确的collection_name/source清理旧知识记录后重启；不要删除聊天记忆、好感度或整个数据库。

## 可选确定性工具

examples/nonebot_song.py提供固定查曲命令；examples/mcp_server.py提供只读search_song。它们不随知识库自动启用，接入说明见[NoneBot示例](corpus/maimai_dev/09_NoneBot查曲示例.md)与[MCP示例](corpus/maimai_dev/11_MCP与只读工具.md)。MCP额外安装mcp>=2.3,<3，NoneBot示例使用现有NoneBot2与OneBot V11环境。

本地插件集成验证可执行：

```bash
python scripts/integration_check.py --plugin-project ../nonebot-plugin-soruto-ai
```

此命令需要已安装ナナセ开发依赖，会运行真实插件BM25、加载一个NoneBot示例响应器及本地stdio MCP；不连接数据库、QQ或模型。--extra-site可指定隔离依赖目录。

## 已知数据差异

两源共检测到**2069处显示等级差异**，全部保留在data/discrepancies.json。不能把落雪定数强行贴成“国服当前官方定数”；国服NET快照本身只提供显示等级。原始别名中有16个ID未出现在歌曲快照，保留清单但不生成虚构歌曲。采集时有55张日期尚未到的谱面、1首disabled记录，均有标记。

新曲、删曲、版本更新和限时活动会变化。固定快照能证明“采集时来源返回了什么”，不能替代当天官方公告或本人账号解锁查询。进一步证据与日期见[SOURCES.md](SOURCES.md)。
