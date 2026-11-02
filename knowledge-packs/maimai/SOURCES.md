# 来源与可核实范围

核查日期：2026-11-01。文档以原创中文组织，示例谱与程序为本包自编，不整段转载攻略或第三方代码。歌曲、艺术家、定数、物量等事实型资料保留来源；不包含音乐、曲绘、歌词或商业客户端文件。

## 原始数据

| 来源 | 取得内容与口径 |
| --- | --- |
| [落雪公共曲目接口](https://maimai.lxns.net/api/v0/maimai/song/list?notes=true) | 1360条、5623谱面；含utage、未配信和disabled，不能一概当作已可游玩 |
| [落雪公共别名接口](https://maimai.lxns.net/api/v0/maimai/alias/list) | 1072条别名记录，其中可关联到本次歌曲的别名共2933个 |
| [落雪接口文档](https://maimai.lxns.net/docs/api/maimai) | 字段定义、ID与类型、B35/B15、配信日期、个人接口权限 |
| [CrazyKidCN国服曲库固定提交](https://github.com/CrazyKidCN/maimaiDX-CN-songs-database/blob/0426b05134ec9d7858aeb2aed3131754699b19f4/maidata.json) | 1294首与5520张常规谱面显示等级；无小数定数 |
| [国服曲库项目站](https://maimai-net.cn/database) | 页面标CN1.56-F、2026-10-30；仓库README仍写CN1.56-E/10-01，保留这一标识差异 |

原始响应与来源标识在data，完整内容哈希在manifest.json。规范化仅做可说明的关联，未覆盖/缺失不自动解释为删曲。国服NET资料由社区项目采集，不是本包直接登录官方账号所得。

本次水鱼公开/music_data连接未完成；另一个公开镜像JSON解析失败，因此两者都未作为交付曲库快照。没有以失败请求或不完整响应冒充成功采集。

## 官方规则与地区资料

- [SEGA国际服玩法介绍](https://maimai.sega.com/play/)：机台基本形式与账号入口。
- [SEGA国际服基础操作](https://maimai.sega.com/play/howto/)：基础音符、操作与通关概念。
- [SEGA国际服其他要素1](https://maimai.sega.com/play/newfunction2/)：Rating分池概念、友人对战、宴会场等。
- [SEGA国际服其他要素2](https://maimai.sega.com/play/newfunction3/)：旅行任务、段位、挑战、部分社交玩法。
- [SEGA国际服新功能](https://maimai.sega.com/play/newfunction/)：版本新增要素；新界面规则不能套用旧版本推测。
- [SEGA国际服版本公告](https://maimai.sega.com/)：CiRCLE/CiRCLE PLUS对应地区发售日期。
- [SEGA日服玩法页](https://maimai.sega.jp/play/)：核查时页面标题为MAGiCAL；浏览工具对部分子页正文未能提取，不声称已全面核实这些子页细则。
- [SEGA DX1.02-A计分调整](https://maimai.sega.jp/news/2019-08-07/)：BREAK额外分调整的历史依据。
- [SEGA DX1.11判定选项说明](https://maimai.sega.jp/news/2020-09-24/)：A/B的历史功能说明。
- [SEGA DX PLUS说明](https://maimai.sega.jp/news/2020-01-15/)：版本牌子、新旧池与曲库调整的历史依据，不作2026所有例外的总表。
- [KoP8日服舞萌规则](https://maimai.sega.jp/kop8th/maimai/)：特定届次预选与修订示例，不代表国服赛制。

国际服歌曲页在核查时自标最后更新2023-01-18，因此没有用该页充当2026全曲库。[页面原说明](https://maimai.sega.com/song/)

## 社区规则、代码与格式

- [国服万花筒社区攻略](https://maimai-net.cn/kaleidxscope)：门曲和条件概览，仅摘要；具体名单、日期与计数例外需要复查原页。
- [水鱼固定算法源码](https://github.com/Diving-Fish/maimaidx-prober/blob/01593811b106b50594ed71026b75ba29a74d6806/database/models/maimai.py)：本包Rating profile及数据序列化依据，提交日期2026-08-18。没有复制其函数实现；使用原创Decimal实现。
- [水鱼公开API](https://github.com/Diving-Fish/maimaidx-prober/blob/main/doc/docs/developer/zh-api-document.md)、[OAuth](https://github.com/Diving-Fish/maimaidx-prober/blob/main/doc/docs/developer/oauth-api-document.md)、[迁移说明](https://github.com/Diving-Fish/maimaidx-prober/blob/main/doc/docs/developer/oauth-migration.md)：公共/个人端点边界与旧接口迁移，文档可能后续变更。
- [水鱼项目说明](https://github.com/Diving-Fish/maimaidx-prober)：数据导入与准确性边界。
- [simai作者维护的格式](https://w.atwiki.jp/simai/pages/1003.html)：社区谱面记法；本包仅用原创短例子讲解。
- [MaiLib](https://github.com/Neskol/MaiLib)：完整解析器工程的参考入口，未嵌入其源代码。
- [MaiMuriDX开发研究](https://github.com/Minepig/MaiMuriDX/blob/master/docs/开发笔记.md)：社区计分与传感器研究，不能称作SEGA官方说明。
- [NoneBot插件](https://nonebot.dev/docs/tutorial/create-plugin)、[OneBot V11消息段](https://github.com/botuniverse/onebot-11/blob/master/message/segment.md)、[MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)、[Python Decimal](https://docs.python.org/3/library/decimal.html)：原创代码例子的接口和计算背景。

## 如何维护可信度

每次更新保留来源URL、采集时间、原始内容哈希和差异清单。官方公告描述官方规则，社区接口只证明它自己的数据。练习建议和程序设计意见已按原创方法表述，不包装成官方结论。没有核实的具体判定毫秒窗口、逐门完整名单、个人实时账号状态与完整官方谱面不补写为事实。
