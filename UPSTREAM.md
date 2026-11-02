# 来源与迁移范围

来源：[sbga-fake/maimaibots](https://github.com/sbga-fake/maimaibots/tree/6bf9ad2335d81c416950798a89c52c3d32f81651/soruto/astrbot_plugin_soruto_ai)，基准提交 `6bf9ad2335d81c416950798a89c52c3d32f81651`。

人格提示、禁用词、会话聚合、记忆相关性、好感度及会话命令逻辑源自上游；NoneBot 入口、QQ 发送、数据库初始化、DeepSeek API、搜索、MCP、Skills、知识库及测试适配由本次迁移实现。保留上游作者 maimaibots 的来源记录。上游目录未附单独许可证，本文件不另行声明上游内容的授权条款。

目标仅为所链接 AI 插件。`/persecute` 和复读插件属于相邻目录，不在本插件内实现，帮助不宣称提供它们。Telegram 文件 ID 替换为对应 emoji；不依赖 AstrBot 或 python-telegram-bot。

用户确认：独立发布结构；QQ OneBot V11；全新 MySQL/MariaDB 数据；保留人格、好感度、主动闲聊；DeepSeek 官方 API；Flash 日常/策略/摘要/视觉，Pro 复杂问答；Skills 不执行本地脚本，仅用搜索及配置的 MCP 工具；独立群白名单，获准群成员自动登记，私聊仅已登记未封禁者。

此项目与父目录的舞萌账号插件独立安装、独立配置、独立数据库表，不自动启动父项目或连接生产数据库。

后续用户要求（0.1.1）：机器人名称改为「ナナセ」，取消22:00—06:00不主动参与群聊的规则，全天沿用相同的内容判断、个人开关和闲聊去重。包名、环境变量和数据库表名保持兼容；其余人格背景沿用此前确认范围。
